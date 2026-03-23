# Operations

This document describes how NV Local is typically run in development and how it is deployed in production-like environments.

## Environments

- Local dev: run `python main.py` or `python run_cli_main.py` from a virtualenv
- Container: build and run `docker/Dockerfile`
- CI/CD: GitHub Actions builds and pushes a container image to Azure Container Registry

## Configuration And Secrets

Core runtime secrets:

- `OPENAI_API_KEY`
- `BRAVE_SEARCH_API_KEY`

Optional features:

- Twitter MCP: `TWITTER_API_KEY`, `TWITTER_BEARER_TOKEN`
- Email delivery: `SUPABASE_URL`, `SUPABASE_KEY`, `SMTP_EMAIL`, `SMTP_APP_PASSWORD`

Operational guidance:

- Prefer injecting secrets via your environment (shell export, container env vars, or Azure Key Vault).
- `run_cli_main.py` calls `dotenv.load_dotenv()`; `main.py` does not.

## Deployments

### Container Image Build + Push

GitHub workflow: `/.github/workflows/push-container-to-azure.yml`

- Trigger: pushes to `main`, but the job only runs when either:
  - the commit message is exactly `release`, or
  - the workflow is run manually via `workflow_dispatch`
- Output: image pushed to Azure Container Registry with two tags:
  - `<login_server>/next-voters-local:<git_sha>`
  - `<login_server>/next-voters-local:latest`

### Runtime (Azure)

The repo contains an Azure infrastructure diagram in `__diagrams__/azure-infrastructure.mmd`. The intended model is:

- An Azure Container Apps Job pulls the image from ACR
- A schedule triggers the job
- Logs are emitted to stdout/stderr and collected by Azure Monitor / Log Analytics

This repository does not include IaC for provisioning the Azure resources.

## Logging And Monitoring

- Primary logs: stdout/stderr from the container/job
- Failures: per-city pipeline failures are captured and surfaced as `error` fields in the multi-city results

If email sending is enabled:

- A JSON file of delivery failures may be written (`email_failures.json`). In ephemeral containers this file is not durable unless you mount storage or ship logs elsewhere.

## Data Storage And Backups

- The core pipeline is stateless; it does not persist reports by default.
- Email subscriber list is read from Supabase (table: `subscriptions`, column: `contact`). Backups, retention, and schema migrations are owned by the Supabase project.

## Runbooks

### Job Fails Immediately

1) Check logs for missing env vars (common: `OPENAI_API_KEY` or `BRAVE_SEARCH_API_KEY`).
2) If using `python main.py` locally, confirm your shell exports env vars (it does not auto-load `.env`).

### Brave Search Errors

Symptoms: errors mentioning `BRAVE_SEARCH_API_KEY` or failures in the MCP client.

1) Verify the key is present in the runtime environment.
2) Confirm outbound network access to `https://server.smithery.ai/`.
3) If failures are intermittent, consider retries or reducing concurrency.

### OpenAI Errors / Rate Limits

1) Verify `OPENAI_API_KEY` and account quota.
2) If rate-limited, reduce the number of cities run concurrently (edit `data/__init__.py`) or tune model usage.

### Email Not Sending

1) Email delivery is skipped unless all of `SMTP_EMAIL`, `SMTP_APP_PASSWORD`, `SUPABASE_URL`, `SUPABASE_KEY` are set.
2) Confirm Supabase has rows in `subscriptions` with a non-empty `contact`.
3) For Gmail SMTP, ensure an app password is used and SMTP access is permitted.
