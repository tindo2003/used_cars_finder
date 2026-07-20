# AWS deployment

Moves the scraper + notify cron jobs off GitHub Actions onto ECS Fargate (scheduled via EventBridge Scheduler), and hosts the frontend on App Runner. Supabase stays as-is for DB/Auth/RLS -- this only changes where the *compute* runs.

## What this creates

- 2 ECR repos (`used-cars-finder-scraper`, `used-cars-finder-frontend`)
- 1 ECS cluster (Fargate, no EC2/servers to manage) + 2 task definitions (`scrape`, `notify`, same image, different command)
- 2 EventBridge Scheduler rules mirroring `scraper.yml`'s `*/15 * * * *` and `notify.yml`'s `0 15 * * *` crons
- 3 Secrets Manager secrets (`SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `RESEND_API_KEY`)
- 1 App Runner service for the frontend, auto-deploying on every push to the frontend's ECR repo
- IAM: an ECS task execution role, an EventBridge Scheduler execution role, an App Runner ECR-access role, and a GitHub Actions OIDC role (no AWS access keys stored in GitHub)
- 1 CloudWatch alarm path: any Fargate task that stops with a non-zero exit code publishes to an SNS topic, emailed to `alert_email`

No NAT Gateway (tasks only need outbound internet, run in public subnets with a public IP instead -- see `networking.tf`'s comment for why that's fine here).

## Bootstrap order (first-time setup)

This has a chicken-and-egg step: the ECS task definitions and the App Runner service both reference a `:latest` image tag that doesn't exist until CI has pushed at least once. `terraform apply` will still succeed either way (AWS doesn't validate the image at registration time) -- the scheduled tasks and App Runner deploy just won't actually work until an image exists.

1. **Copy `terraform.tfvars.example` to `terraform.tfvars`** and fill in real values (or pass them via `TF_VAR_*` env vars instead -- either way, never commit the filled-in file; it's gitignored).
2. `terraform init && terraform apply` -- creates everything, including the ECR repos and the GitHub Actions IAM role.
3. **Configure the GitHub repo** (Settings → Secrets and variables → Actions → Variables tab) with:
   - `AWS_GITHUB_ACTIONS_ROLE_ARN` = the `github_actions_role_arn` output from step 2
   - `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` = same values already in use locally (these are safe as plain repo *variables*, not secrets -- they're already public in the shipped frontend bundle)
4. **Push to `main`** (or run the `Deploy to AWS` workflow manually via `workflow_dispatch`) -- this builds and pushes both images for the first time, and registers the first real task definition revisions.
5. **Verify before cutting over**: manually run each ECS task once (`aws ecs run-task --cluster used-cars-finder-cluster --task-definition used-cars-finder-scrape ...`, matching network config from `scheduler.tf`) and check CloudWatch Logs. Check the App Runner service URL (`terraform output apprunner_service_url`) loads correctly.
6. **Only after that's confirmed working**: disable the `schedule:` trigger in `.github/workflows/scraper.yml` and `.github/workflows/notify.yml` (keep `workflow_dispatch` in both as a manual fallback). Until you do this, both the old GitHub Actions cron *and* the new AWS schedule will run in parallel -- harmless (the scraper's upsert logic is idempotent) but redundant.

## Redeploying after this

Every push to `main` that touches `scraper/**` rebuilds+pushes the scraper image and registers new task definition revisions automatically; the very next scheduled run picks up the new image (EventBridge targets the task-definition *family*, not a pinned revision). Every push touching the frontend rebuilds+pushes that image, and App Runner auto-deploys it. Nothing about this Terraform config needs to change or be re-applied for routine code changes -- only for infrastructure changes (new secrets, schedule changes, scaling changes, etc).
