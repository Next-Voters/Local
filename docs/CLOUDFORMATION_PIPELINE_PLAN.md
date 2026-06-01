# CloudFormation Infrastructure Pipeline — Engineering Decisions

> **Status**: In progress (`cloudformation-refactor` branch)
> **Last updated**: 2026-05-29
> **Scope**: Full AWS stack codified in CloudFormation with staging/production separation

---

## 1. Problem Statement

All AWS infrastructure is provisioned manually. The existing CI pipeline (`.github/workflows/push-image-to-ecr.yml`) only builds a Docker image, pushes to ECR, and updates the ECS task definition via raw `aws ecs` CLI calls. There is no infrastructure-as-code, no IAM validation, no staging environment, and no pre-deployment safety gate.

---

## 2. IaC Tool Selection

### Decision: AWS CloudFormation over Terraform

### Rationale

- The infrastructure is 100% AWS. Terraform's multi-cloud abstraction provides no value here.
- CloudFormation eliminates the bootstrap problem — no S3 state bucket or DynamoDB lock table required. State management is automatic.
- Native day-one support for all AWS services. No provider version mismatches.
- Built-in drift detection without running a separate command.
- Change Sets provide the same "preview before apply" workflow as `terraform plan`.

### Rejected Alternative: Terraform + LocalStack

- **LocalStack was evaluated as a staging environment** and rejected. LocalStack emulates AWS APIs but does not reproduce AWS behavior faithfully. IAM enforcement is weak or off by default, many services are partial or stubbed, and a passing LocalStack run does not predict whether `terraform apply` will succeed against real AWS.
- **Specific failure modes LocalStack cannot catch**: IAM permission gaps, cross-account/VPC networking, service-linked roles, KMS key policies, resource quotas, region availability.
- **LocalStack's valid use case** is fast, free, offline iteration and CI that validates HCL parses and plans cleanly. It is a test harness, not a staging environment.

### Tradeoffs Accepted

- CloudFormation templates are more verbose than HCL.
- Deploys are slower (sequential resource provisioning vs Terraform's parallel execution).
- Rollback failures (`ROLLBACK_FAILED` state) require manual intervention.
- AWS vendor lock-in (acceptable — the project is already all-in on AWS).

---

## 3. Environment Architecture

### Decision: Two separate AWS accounts (staging + production)

### Account Structure

```
AWS Organization
├── Staging Account
│   ├── ECR (staging images)
│   ├── ECS Fargate (staging tasks)
│   ├── SQS (staging queues)
│   ├── Lambda (staging dispatcher + email)
│   ├── SES (test sender address)
│   ├── SUPABASE_URL → staging Supabase DB
│   └── SUPABASE_KEY → staging Supabase key
│
└── Production Account
    ├── ECR (prod images)
    ├── ECS Fargate (prod tasks)
    ├── SQS (prod queues)
    ├── Lambda (prod dispatcher + email)
    ├── EventBridge Scheduler (weekly cron) ← prod only
    ├── SES (real sender address)
    ├── SUPABASE_URL → production Supabase DB
    └── SUPABASE_KEY → production Supabase key
```

### Access Model

- **Staging**: Open to all team members. No customer/user relies on staging resources. Safe to break, experiment, and test freely.
- **Production**: Restricted to senior management. Protected by IAM Identity Center permission sets.

### Separate Supabase Databases

- Each account connects to its own Supabase database instance.
- Staging pipeline writes to the staging DB; staging Email Lambda reads from the staging DB and sends to a test inbox.
- This prevents staging runs from writing test data into production `reports`/`report_headers` tables or triggering emails to real subscribers.

---

## 4. EventBridge Scheduler

### Decision: Production only — no scheduler in staging

### Rationale

- The scheduler's only function is invoking the Dispatcher Lambda on a cron. There is no business logic to test.
- A staging scheduler running on autopilot burns OpenAI and Tavily API credits with no one watching the output.
- Staging pipeline runs are invoked manually: `aws lambda invoke --function-name nv-staging-dispatcher out.json`
- This is implemented via `Condition: IsProd` in the CloudFormation template.

---

## 5. CloudFormation Template Design

### Decision: One template, parameterized for both environments

### File Structure

```
infrastructure/
  template.json               # Single template for both environments
  parameters/
    staging.json              # Staging-specific parameter values
    production.json           # Production-specific parameter values
```

### Parameterization Strategy

- The `Environment` parameter (`staging` | `production`) drives all resource naming via `Fn::Sub`: `next-voters-${Environment}-*`.
- Resources that only exist in production use `Condition: IsProd`.
- Sensitive values (API keys, Supabase credentials) are stored in AWS Secrets Manager or SSM Parameter Store per account, referenced via `{{resolve:secretsmanager:...}}` dynamic references. They do NOT go in parameter files.
- Parameter files contain only non-sensitive config (environment name, SES domain, sender email).

### Deployment Commands

```bash
# Deploy to staging
aws cloudformation deploy \
  --template-file infrastructure/template.json \
  --parameter-overrides file://infrastructure/parameters/staging.json \
  --stack-name next-voters-staging \
  --capabilities CAPABILITY_NAMED_IAM

# Deploy to production
aws cloudformation deploy \
  --template-file infrastructure/template.json \
  --parameter-overrides file://infrastructure/parameters/production.json \
  --stack-name next-voters-production \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## 6. Resources Codified

### All resources in `infrastructure/template.json`:

| Resource | Type | Notes |
|----------|------|-------|
| VPC | `AWS::EC2::VPC` | 10.0.0.0/16 |
| Public Subnet A | `AWS::EC2::Subnet` | Multi-AZ, public IP on launch |
| Public Subnet B | `AWS::EC2::Subnet` | Multi-AZ, public IP on launch |
| Internet Gateway | `AWS::EC2::InternetGateway` | Attached to VPC |
| Route Table + Routes | `AWS::EC2::RouteTable`, `AWS::EC2::Route` | 0.0.0.0/0 → IGW |
| Security Group | `AWS::EC2::SecurityGroup` | Egress all, ingress none |
| Pipeline ECR Repo | `AWS::ECR::Repository` | `next-voters-${Environment}-agent` |
| Dispatcher ECR Repo | `AWS::ECR::Repository` | `next-voters-${Environment}-dispatcher` |
| Email ECR Repo | `AWS::ECR::Repository` | `next-voters-${Environment}-email` |
| ECS Log Group | `AWS::Logs::LogGroup` | 30-day retention |
| Dispatcher Log Group | `AWS::Logs::LogGroup` | 30-day retention |
| Email Log Group | `AWS::Logs::LogGroup` | 30-day retention |
| Report Queue | `AWS::SQS::Queue` | 300s visibility, redrive → Email DLQ after 3 failures |
| Pipeline DLQ | `AWS::SQS::Queue` | 14-day retention, standalone |
| Email DLQ | `AWS::SQS::Queue` | 14-day retention |
| SES Domain Identity | `AWS::SES::EmailIdentity` | Requires manual DNS verification |
| ECS Task Execution Role | `AWS::IAM::Role` | Trust: ecs-tasks.amazonaws.com. ECR pull, CloudWatch logs |
| ECS Task Role | `AWS::IAM::Role` | Trust: ecs-tasks.amazonaws.com. `sqs:SendMessage` to report queue + pipeline DLQ |
| Dispatcher Lambda Role | `AWS::IAM::Role` | Trust: lambda.amazonaws.com. `ecs:RunTask`, `iam:PassRole`, CloudWatch logs |
| Email Lambda Role | `AWS::IAM::Role` | Trust: lambda.amazonaws.com. `sqs:ReceiveMessage/DeleteMessage`, `ses:SendEmail`, CloudWatch logs |
| EventBridge Scheduler Role | `AWS::IAM::Role` | Trust: scheduler.amazonaws.com. `lambda:InvokeFunction`. **Prod only** |
| GitHub Actions OIDC Provider | `AWS::IAM::OIDCProvider` | Trusts `token.actions.githubusercontent.com` |
| GitHub Actions Role | `AWS::IAM::Role` | Trust: GitHub OIDC. ECR push, ECS task def registration, CloudFormation deploy |
| ECS Cluster | `AWS::ECS::Cluster` | Fargate capacity provider |
| ECS Task Definition | `AWS::ECS::TaskDefinition` | 1 vCPU / 2GB, awsvpc, container wired to SQS URLs and log group |
| Dispatcher Lambda | `AWS::Lambda::Function` | Container image, 256MB, 300s timeout |
| Email Lambda | `AWS::Lambda::Function` | Container image, 256MB, 60s timeout, reserved concurrency 5 |
| Email SQS Trigger | `AWS::Lambda::EventSourceMapping` | Report queue → Email Lambda, batch size 1 |
| Weekly Scheduler | `AWS::Scheduler::Schedule` | `cron(0 9 ? * MON *)`. **Prod only** |

---

## 7. CI/CD Pipeline Design

### Decision: Fail-fast ordering with staging gate before production

### Pipeline Stages

```
PR push (both staging and prod validation):
  1. Lint + format               (seconds)  ─┐ parallel
  2. Compile check               (seconds)  ─┘
  3. Static policy analysis      (seconds, after 1+2)
     - cfn-lint: CloudFormation template validation
     - checkov: IAM policy static analysis

Merge to main:
  4. Deploy to staging account   (minutes, OIDC auth via AWS_ROLE_ARN_STAGING)
  5. Smoke test staging          (optional — invoke staging dispatcher, verify pipeline completes)
  6. Deploy to prod account      (minutes, OIDC auth via AWS_ROLE_ARN_PROD, manual approval gate)
```

### CI Authentication

- Two OIDC roles, one per account: `secrets.AWS_ROLE_ARN_STAGING` and `secrets.AWS_ROLE_ARN_PROD`.
- CI assumes one role, deploys to that account, then assumes the other.
- The GitHub Actions OIDC provider and role are defined in the CloudFormation template itself.

### Existing Workflow

- `.github/workflows/push-image-to-ecr.yml` will be replaced/absorbed into the new pipeline.
- Its build+push+task-def-update logic moves into the deploy stage.
- Current GitHub vars used: `AWS_REGION`, `ECR_REPOSITORY`, `ECS_TASK_FAMILY`, `ECS_CONTAINER_NAME`.
- Current secret: `AWS_ROLE_ARN` (will split into `_STAGING` and `_PROD`).

---

## 8. IAM Validation Strategy

### Three Layers

| Layer | Tool | Runs When | What It Catches |
|-------|------|-----------|-----------------|
| Static template validation | `cfn-lint` | Every PR | Malformed CloudFormation, invalid resource properties |
| Static policy analysis | `checkov` | Every PR | Over-permissioned IAM policies, `*:*` wildcards, missing encryption |
| Runtime permission verification | `iam:SimulatePrincipalPolicy` | Post-deploy to staging | Roles that are syntactically valid but deny required actions at runtime |

### IAM Policy Simulator

- Runs against the staging account after CloudFormation deploy.
- Calls `aws iam simulate-principal-policy` for each role with its expected actions.
- Actions derived from actual code usage (e.g., `sqs:SendMessage` from `utils/sqs_client.py`).
- Fails the pipeline if any expected permission is denied.

### Why Not HCL/CloudFormation-Level IAM Validation

- CloudFormation declares policies; it does not evaluate them.
- There is no template syntax that answers "will this Lambda actually be able to send this email at runtime."
- Only the IAM Policy Simulator (or actually running the code) can answer runtime permission questions.

---

## 9. Manual Setup Required (One-Time)

These items cannot be automated by CloudFormation because they must exist before the first stack deploy:

| Item | Time | Why Manual |
|------|------|-----------|
| AWS Organization + staging/prod member accounts | ~15 min | Accounts are the containers everything lives in |
| IAM Identity Center (SSO) + permission sets | ~20 min | Control plane above individual accounts |
| SES domain DNS verification records | ~10 min | DNS provider is external to AWS (add CNAME records for DKIM) |
| Initial container images in each ECR repo | ~15 min | Lambda functions reference `image_uri` — empty repos cause deploy failure |
| Budget alert on staging account | ~2 min | Catch runaway costs early (set at $20 threshold) |

### NOT Required Manually (CloudFormation Handles)

- S3 state bucket (not needed — CloudFormation manages its own state)
- DynamoDB lock table (not needed — CloudFormation handles concurrency)
- OIDC provider for GitHub Actions (defined in the template)
- All IAM roles and policies
- All compute, networking, messaging, and logging resources

---

## 10. Key File References

| File | Relevance |
|------|-----------|
| `infrastructure/template.json` | CloudFormation template (created on `cloudformation-refactor` branch) |
| `infrastructure/parameters/staging.json` | Staging parameter values (contains PLACEHOLDERs to fill) |
| `infrastructure/parameters/production.json` | Production parameter values (contains PLACEHOLDERs to fill) |
| `.github/workflows/push-image-to-ecr.yml` | Existing CI workflow to be replaced |
| `docs/AWS_ARCHITECTURE.md` | Authoritative architecture reference and service flow diagram |
| `utils/sqs_client.py` | Confirms IAM actions ECS task role needs (`sqs:SendMessage` at lines 55, 89) |
| `docker/Dockerfile` | Container definition the ECS task definition must match |
| `.env.example` | Environment variables that map to ECS task definition config |

---

## 11. Open Items

- [ ] Fill `PLACEHOLDER` values in `infrastructure/parameters/staging.json` and `production.json`
- [ ] Create AWS Organization with staging and prod member accounts
- [ ] Set up IAM Identity Center with staging-open / prod-restricted permission sets
- [ ] Add SES DKIM DNS records after first deploy outputs DKIM tokens
- [ ] Build and push initial container images to each ECR repo before first CloudFormation deploy
- [ ] Create CI/CD workflow (`.github/workflows/ci-cd.yml`) with staging → prod deploy stages
- [ ] Write IAM Policy Simulator script (`scripts/iam-policy-simulator.sh`)
- [ ] Set budget alert on staging account
- [ ] Delete or archive `.github/workflows/push-image-to-ecr.yml` after new pipeline is live
