# Terraform IaC Pipeline Plan

## Context

All AWS infrastructure for the Next Voters pipeline is currently provisioned manually. The existing CI (`.github/workflows/push-image-to-ecr.yml`) only builds a Docker image, pushes to ECR, and updates the ECS task definition via raw `aws ecs` CLI calls. There is no infrastructure validation, no IAM policy checking, and no pre-deployment safety gate.

This plan codifies the entire AWS stack in Terraform and builds a CI/CD pipeline with three validation layers:
1. **LocalStack** -- fast, free, per-PR structural validation (resources create without errors)
2. **Static policy analysis** -- checkov + tf-policy-validator catch malformed/over-permissioned IAM policies
3. **IAM Policy Simulator** -- post-merge, pre-deploy gate that calls real AWS to verify runtime permissions

---

## Pipeline Stage Order (fail fast, fail cheap)

```
PR push:
  1. Lint + format        (seconds, zero compute)
  2. Compile check        (seconds, Python only)
  3. LocalStack + tflocal (minutes, Docker sidecar)  --+-- parallel after 1+2
  4. Static policy analysis (seconds, checkov)        --+

Merge to main:
  5. IAM Policy Simulator (seconds, real AWS creds)
  6. Build + push Docker image to ECR
  7. Terraform apply to production
```

Stages 1-2 run in parallel. Stages 3-4 run in parallel after 1+2 pass. Stages 5-7 are sequential, merge-to-main only.

---

## Terraform Directory Structure

```
terraform/
  versions.tf                 # Terraform >= 1.9, AWS provider ~> 5.0
  backend.tf                  # S3 backend (partial config, completed by -backend-config)
  provider.tf                 # AWS provider, default tags, NO LocalStack-specific config
  variables.tf                # Root inputs (region, project_name, environment, etc.)
  outputs.tf                  # Root outputs (role ARNs, queue URLs, cluster ARN)
  data.tf                     # aws_caller_identity, aws_region data sources
  main.tf                     # Root composition -- wires all child modules
  terraform.tfvars            # Production values
  localstack.tfvars           # LocalStack overrides (dummy domain, test email)

  modules/
    networking/               # VPC, 2 public subnets, IGW, route tables, SG (egress-only)
    ecr/                      # 3 repos: next-voters-agent, lambda-dispatcher, lambda-email
    iam/                      # 6 roles: ECS task exec, ECS task, 2x Lambda, EventBridge, GH Actions OIDC
      policies/               # JSON policy templates (templatefile sources)
    ecs/                      # Cluster (Fargate) + task definition (no service -- ad-hoc launch)
    lambda/                   # Dispatcher + Email Lambda + SQS event source mapping
    sqs/                      # Report-ready queue, Pipeline DLQ, Email DLQ + redrive policies
    eventbridge/              # Scheduler rule (weekly cron -> Dispatcher Lambda)
    ses/                      # Domain identity + DKIM
    cloudwatch/               # 3 log groups: ECS pipeline, Dispatcher Lambda, Email Lambda

scripts/
  iam-policy-simulator.sh     # Post-merge IAM validation via iam:SimulatePrincipalPolicy
  policy-validator-config.yaml # tf-policy-validator deny rules (no iam:*, no *:*)
```

Each module follows the standard `main.tf` / `variables.tf` / `outputs.tf` pattern.

---

## Module Breakdown

### `modules/networking/`
- `aws_vpc.main` (10.0.0.0/16)
- `aws_subnet.public` x2 (multi-AZ, for Fargate tasks with public IP + IGW)
- `aws_internet_gateway.main`, route tables, associations
- `aws_security_group.ecs_tasks` (egress all, ingress none -- tasks call external APIs, receive nothing)

### `modules/ecr/`
- `aws_ecr_repository` (for_each: `next-voters-agent`, `lambda-dispatcher-pipelines`, `lambda-email-sender`)
- `aws_ecr_lifecycle_policy` -- retain last 10 tagged images, expire untagged after 7 days

### `modules/iam/`
6 IAM roles with least-privilege policies:

| Role | Trust Principal | Key Permissions |
|------|----------------|-----------------|
| `ecs-task-execution` | ecs-tasks.amazonaws.com | ECR pull, CloudWatch logs, Secrets Manager read |
| `ecs-task` | ecs-tasks.amazonaws.com | `sqs:SendMessage` to report queue + pipeline DLQ (from `utils/sqs_client.py:55,89`) |
| `dispatcher-lambda` | lambda.amazonaws.com | `ecs:RunTask`, `iam:PassRole`, CloudWatch logs |
| `email-lambda` | lambda.amazonaws.com | `sqs:ReceiveMessage/DeleteMessage`, `ses:SendEmail`, CloudWatch logs |
| `eventbridge-scheduler` | scheduler.amazonaws.com | `lambda:InvokeFunction` on Dispatcher |
| `github-actions-oidc` | token.actions.githubusercontent.com | ECR push, ECS describe/register task def |

Policy documents live in `modules/iam/policies/` as JSON templates using `templatefile()`.

**Circular dependency handling**: Roles are created without policies first. Policies are attached as separate `aws_iam_role_policy` resources, receiving target resource ARNs via module variables. Terraform's dependency graph resolves this. For the ECS task definition ARN (includes revision number), use a wildcard pattern in the policy.

### `modules/ecs/`
- `aws_ecs_cluster.main` (Fargate capacity provider)
- `aws_ecs_task_definition.pipeline` -- 1 vCPU / 2GB, references `next-voters-agent` ECR image, `REGION` env var set at runtime by Dispatcher Lambda

No ECS service -- tasks are launched ad-hoc by the Dispatcher Lambda.

### `modules/lambda/`
- `aws_lambda_function.dispatcher` -- container image from `lambda-dispatcher-pipelines` ECR, 256MB, 300s timeout
- `aws_lambda_function.email_sender` -- container image from `lambda-email-sender` ECR, 256MB, 60s timeout
- `aws_lambda_event_source_mapping.email_sqs` -- maps report-ready queue -> Email Lambda, batch size 1

Note: Lambda source code is NOT in this repo. These modules reference existing ECR image URIs as variables.

### `modules/sqs/`
- `aws_sqs_queue.report_ready` -- 300s visibility timeout, redrive to Email DLQ after 3 failures
- `aws_sqs_queue.pipeline_dlq` -- 14-day retention, standalone
- `aws_sqs_queue.email_dlq` -- 14-day retention, redrive target

### `modules/eventbridge/`
- `aws_scheduler_schedule.weekly_pipeline` -- EventBridge Scheduler v2, `cron(0 9 ? * MON *)`, target: Dispatcher Lambda

### `modules/ses/`
- `aws_ses_domain_identity`, `aws_ses_domain_dkim`, `aws_ses_email_identity`

### `modules/cloudwatch/`
- 3 `aws_cloudwatch_log_group` resources (ECS, Dispatcher Lambda, Email Lambda), 30-day retention

---

## Backend Configuration

- **Production**: S3 backend with DynamoDB state locking. Partial config in `backend.tf`, completed at init time via `-backend-config` flags (bucket name, key, region, DynamoDB table).
- **LocalStack (CI)**: `terraform init -backend=false` -- local ephemeral state, discarded when the runner exits.
- **Bootstrap**: S3 bucket + DynamoDB table for state must be created manually before first `terraform init`. One-time operation.

---

## Provider Configuration

`provider.tf` contains a clean AWS provider with `default_tags` -- no LocalStack-specific config. `tflocal` (installed via `pip install terraform-local`) wraps the `terraform` CLI and automatically injects LocalStack endpoint overrides + dummy credentials at runtime. This keeps `.tf` files environment-agnostic.

---

## CI/CD Workflow (`.github/workflows/ci-cd.yml`)

Replaces the existing `push-image-to-ecr.yml`. Absorbs its build+push+task-def-update logic into the deploy stage.

### Job structure:

**`lint`** (PR + main) -- parallel with `compile-check`
- Python: `ruff check . && ruff format --check .`
- Terraform: `terraform fmt -check -recursive && terraform init -backend=false && terraform validate`

**`compile-check`** (PR + main) -- parallel with `lint`
- `pip install -r requirements.txt && python -m compileall -q .`

**`localstack-validate`** (PR + main) -- needs: [lint, compile-check]
- GitHub Actions `services:` runs LocalStack as a sidecar container
- `pip install terraform-local`
- `tflocal init -backend=false && tflocal plan -var-file=localstack.tfvars -out=tfplan && tflocal apply -auto-approve tfplan`
- Spot-check: `aws --endpoint-url=http://localhost:4566 sqs list-queues` (etc.)

**`policy-analysis`** (PR + main) -- needs: [lint, compile-check], parallel with localstack-validate
- `terraform plan -var-file=localstack.tfvars -out=tfplan && terraform show -json tfplan > tfplan.json`
- `checkov -d terraform/ --framework terraform --soft-fail`
- `tf-policy-validator validate --template-path tfplan.json --config scripts/policy-validator-config.yaml`
- Both start as advisory (soft-fail), tighten over time

**`iam-policy-simulator`** (main only) -- needs: [localstack-validate, policy-analysis]
- OIDC auth to real AWS via `aws-actions/configure-aws-credentials@v5`
- `bash scripts/iam-policy-simulator.sh`

**`build-and-push`** (main only) -- needs: [iam-policy-simulator]
- Same logic as current `push-image-to-ecr.yml`: build Docker image, push to ECR with SHA + latest tags
- Outputs `image_tag: ${{ github.sha }}`

**`deploy`** (main only) -- needs: [build-and-push], environment: production (manual approval gate)
- `terraform init` with prod backend config
- `terraform plan -var-file=terraform.tfvars -var="ecr_image_tag=$SHA" -out=tfplan`
- `terraform apply -auto-approve tfplan`

### Permissions:
- `id-token: write` (OIDC), `contents: read`, `pull-requests: write` (for plan output as PR comment)

### Secrets/variables needed:
- Existing: `secrets.AWS_ROLE_ARN`, `vars.AWS_REGION`, `vars.ECR_REPOSITORY`, `vars.ECS_TASK_FAMILY`, `vars.ECS_CONTAINER_NAME`
- New: none required (Terraform manages resource names directly)

---

## IAM Policy Simulator Script (`scripts/iam-policy-simulator.sh`)

For each of the 5 runtime roles (excludes GitHub Actions OIDC role):
1. Discover role ARN via naming convention (`next-voters-*`) + `aws sts get-caller-identity`
2. Call `aws iam simulate-principal-policy` with the actions the role must have
3. Parse results with `jq`, fail if any action returns `denied`

Actions checked per role (derived from actual code):
- **ECS task role**: `sqs:SendMessage`, `sqs:GetQueueUrl` (from `utils/sqs_client.py`)
- **ECS task execution**: `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `logs:PutLogEvents`
- **Dispatcher Lambda**: `ecs:RunTask`, `iam:PassRole`, `logs:CreateLogStream`
- **Email Lambda**: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `ses:SendEmail`
- **EventBridge scheduler**: `lambda:InvokeFunction`

---

## Existing Infrastructure Migration

Since AWS resources were provisioned manually, first `terraform apply` will try to create duplicates.

**Strategy**:
- Use `terraform import` (or Terraform 1.5+ `import {}` blocks) for stateful resources: ECR repos with images, SQS queues with in-flight messages
- Create-new for stateless resources if naming differs (IAM roles, task definitions)
- Run `terraform plan` after import to verify no destructive diff before first apply

---

## Implementation Order

| Phase | What | Files |
|-------|------|-------|
| 1. Foundation | Root config, versions, provider, variables, data | `versions.tf`, `backend.tf`, `provider.tf`, `variables.tf`, `data.tf`, `*.tfvars` |
| 2. Independent modules | No cross-module deps | `cloudwatch/`, `ecr/`, `networking/`, `sqs/`, `ses/` |
| 3. IAM | Depends on Phase 2 outputs | `iam/` + `policies/` |
| 4. Compute | Depends on IAM + Phase 2 | `ecs/`, `lambda/`, `eventbridge/` |
| 5. Root composition | Wire all modules | `main.tf`, `outputs.tf` |
| 6. CI/CD | Pipeline + validation scripts | `ci-cd.yml`, `iam-policy-simulator.sh`, `policy-validator-config.yaml` |
| 7. Import + cutover | Bring existing resources under Terraform | `terraform import` commands, verify plan, first apply |

---

## Verification Checklist

- [ ] `terraform init -backend=false && terraform validate` passes in `terraform/`
- [ ] `tflocal init -backend=false && tflocal plan -var-file=localstack.tfvars && tflocal apply` succeeds (requires Docker + LocalStack)
- [ ] `checkov -d terraform/ --framework terraform` reports no critical findings
- [ ] `bash scripts/iam-policy-simulator.sh` passes against real AWS
- [ ] PR to main triggers all CI jobs and they pass
- [ ] Merge to main triggers IAM simulator -> build -> deploy chain
- [ ] `terraform plan` against prod shows no unexpected resource destruction after import

---

## Files to Create (44 total)

| Path | Purpose |
|------|---------|
| `terraform/versions.tf` | Provider version constraints |
| `terraform/backend.tf` | S3 backend (partial config) |
| `terraform/provider.tf` | AWS provider + default tags |
| `terraform/variables.tf` | Root input variables |
| `terraform/outputs.tf` | Root outputs |
| `terraform/data.tf` | Data sources |
| `terraform/main.tf` | Root module composition |
| `terraform/terraform.tfvars` | Production values |
| `terraform/localstack.tfvars` | LocalStack overrides |
| `terraform/modules/networking/main.tf` | VPC, subnets, IGW, route tables, SG |
| `terraform/modules/networking/variables.tf` | Networking inputs |
| `terraform/modules/networking/outputs.tf` | Networking outputs |
| `terraform/modules/ecr/main.tf` | 3 ECR repos + lifecycle policies |
| `terraform/modules/ecr/variables.tf` | ECR inputs |
| `terraform/modules/ecr/outputs.tf` | ECR outputs |
| `terraform/modules/iam/main.tf` | 6 IAM roles + policy attachments |
| `terraform/modules/iam/variables.tf` | IAM inputs |
| `terraform/modules/iam/outputs.tf` | IAM outputs |
| `terraform/modules/iam/policies/ecs-task-execution-policy.json` | ECS task execution policy |
| `terraform/modules/iam/policies/ecs-task-policy.json` | ECS task policy (SQS) |
| `terraform/modules/iam/policies/dispatcher-lambda-policy.json` | Dispatcher Lambda policy |
| `terraform/modules/iam/policies/email-lambda-policy.json` | Email Lambda policy |
| `terraform/modules/iam/policies/eventbridge-scheduler-policy.json` | EventBridge scheduler policy |
| `terraform/modules/ecs/main.tf` | Cluster + task definition |
| `terraform/modules/ecs/variables.tf` | ECS inputs |
| `terraform/modules/ecs/outputs.tf` | ECS outputs |
| `terraform/modules/lambda/main.tf` | 2 Lambdas + SQS mapping |
| `terraform/modules/lambda/variables.tf` | Lambda inputs |
| `terraform/modules/lambda/outputs.tf` | Lambda outputs |
| `terraform/modules/sqs/main.tf` | 3 SQS queues + redrive |
| `terraform/modules/sqs/variables.tf` | SQS inputs |
| `terraform/modules/sqs/outputs.tf` | SQS outputs |
| `terraform/modules/eventbridge/main.tf` | Scheduler rule |
| `terraform/modules/eventbridge/variables.tf` | EventBridge inputs |
| `terraform/modules/eventbridge/outputs.tf` | EventBridge outputs |
| `terraform/modules/ses/main.tf` | Domain identity + DKIM |
| `terraform/modules/ses/variables.tf` | SES inputs |
| `terraform/modules/ses/outputs.tf` | SES outputs |
| `terraform/modules/cloudwatch/main.tf` | 3 log groups |
| `terraform/modules/cloudwatch/variables.tf` | CloudWatch inputs |
| `terraform/modules/cloudwatch/outputs.tf` | CloudWatch outputs |
| `.github/workflows/ci-cd.yml` | Full CI/CD pipeline |
| `scripts/iam-policy-simulator.sh` | Post-merge IAM validation |
| `scripts/policy-validator-config.yaml` | tf-policy-validator deny rules |

---

## References

- **Existing CI workflow**: `.github/workflows/push-image-to-ecr.yml`
- **Architecture docs**: `docs/AWS_ARCHITECTURE.md`
- **SQS client (IAM action reference)**: `utils/sqs_client.py`
- **Container definition**: `docker/Dockerfile`
- **Environment variables**: `.env.example`
