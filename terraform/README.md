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

## What each file does

| File | What's in it |
|---|---|
| `versions.tf` | Terraform/provider version constraints, the AWS provider block (region comes from `var.aws_region`), and two data sources (`aws_caller_identity`, `aws_region`) used elsewhere to build ARNs without hardcoding the account ID. |
| `variables.tf` | Every input variable this config takes -- region, project name, GitHub repo/branch (for the OIDC trust policy), the 3 secrets, the alert email, and the two schedule cron expressions. No defaults for anything secret; those must come from `terraform.tfvars` or `TF_VAR_*`. |
| `networking.tf` | Looks up the account's default VPC and its subnets (data sources, doesn't create a VPC), and creates the one security group the Fargate tasks run in -- egress-only, no inbound rule at all, since nothing ever needs to reach these tasks. |
| `ecr.tf` | The 2 ECR repositories (`scraper`, `frontend`) and a shared lifecycle policy that expires anything past the most recent 10 images, so the registry doesn't grow forever. |
| `secrets.tf` | The 3 Secrets Manager secrets (`SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `RESEND_API_KEY`) and their values, sourced from the corresponding Terraform variables. |
| `iam.tf` | Every IAM role in this setup: the ECS task execution role (pulls images, writes logs, reads the 3 secrets), the EventBridge Scheduler execution role (can only `RunTask` on this cluster's two task families), the GitHub Actions OIDC provider + role (so CI never needs stored AWS keys), and the App Runner ECR-access role. Also defines the `local.scrape_task_def_family_arn` / `local.notify_task_def_family_arn` helpers (family-only ARNs, no revision) that `scheduler.tf` and this file's own policies both reference. |
| `ecs.tf` | The ECS cluster itself, 2 CloudWatch log groups, and the 2 task definitions (`scrape` runs `main.py`, `notify` runs `notify.py` -- same image, different `command`). Has a `lifecycle { ignore_changes = [container_definitions] }` on both, since CI re-registers new revisions directly after this initial `apply`, not Terraform. |
| `scheduler.tf` | The 2 EventBridge Scheduler schedules (cron expressions come from `variables.tf`) that actually trigger `RunTask` on a schedule -- this is what replaces `scraper.yml`/`notify.yml`'s GitHub Actions cron. |
| `apprunner.tf` | The App Runner service for the frontend -- pulls from the frontend ECR repo, auto-deploys on new `:latest` pushes. Deliberately doesn't set any runtime env vars here (see the comment in the file for why `NEXT_PUBLIC_*` has to be a Docker build arg instead). |
| `monitoring.tf` | The failure-alert path: an SNS topic + email subscription, and an EventBridge rule that fires on any `ECS Task State Change` event where a container exited non-zero, routed to that SNS topic. |
| `outputs.tf` | The values printed after `apply`/`terraform output` -- both ECR repo URLs, the ECS cluster name, the App Runner URL, and the GitHub Actions role ARN (the one value you paste into the GitHub repo's variables). |
| `terraform.tfvars.example` | Template for the real `terraform.tfvars` (gitignored) -- copy it and fill in real values; never commit the filled-in file. |
| `DEPLOY_PLAYBOOK.md` | Runbook for when `deploy.yml` fails -- known failure modes (a flaky CI-only test, the repo-variable-vs-secret mix-up, the OIDC sub-claim mismatch that silently broke every automated deploy until 2026-07-21), how to verify a deploy actually landed, and how to read the GitHub API without a token/`gh` CLI. |

## Bootstrap order (first-time setup)

This has a chicken-and-egg step: the ECS task definitions and the App Runner service both reference a `:latest` image tag that doesn't exist until CI has pushed at least once. The two behave differently when it doesn't exist yet (confirmed on the real first deploy, see the log below): **ECS task definitions register fine regardless** (AWS doesn't validate the image at registration time -- the scheduled task just fails at *run* time until an image exists), but **`aws_apprunner_service` actually tries to pull and run the image synchronously as part of creating the service**, so `terraform apply` hard-fails with `CREATE_FAILED` if the frontend image doesn't exist in ECR yet. Push the images (step 4 below) before expecting `apply` to fully succeed, or just re-run `terraform apply` (or `terraform apply -replace=aws_apprunner_service.frontend` if it's already stuck in `CREATE_FAILED`) once the image exists.

1. **Copy `terraform.tfvars.example` to `terraform.tfvars`** and fill in real values (or pass them via `TF_VAR_*` env vars instead -- either way, never commit the filled-in file; it's gitignored).
2. `terraform init && terraform apply` -- creates everything, including the ECR repos and the GitHub Actions IAM role. **Expect `aws_apprunner_service.frontend` to fail here on a genuinely fresh deploy** (see the note above) -- everything else will still have been created successfully; that's normal, not a sign anything else is wrong.
3. **Get an image into both ECR repos** before App Runner can succeed. Either push once manually (fastest for a first deploy -- see the log below for the exact `docker build`/`push` commands, including `--platform linux/amd64`, which matters if you're building from an Apple Silicon Mac since Fargate defaults to `X86_64`), or configure the GitHub repo (next step) and push to `main`/run the workflow manually first.
4. **Configure the GitHub repo** (Settings → Secrets and variables → Actions → Variables tab) with:
   - `AWS_GITHUB_ACTIONS_ROLE_ARN` = the `github_actions_role_arn` output from step 2
   - `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` = same values already in use locally (these are safe as plain repo *variables*, not secrets -- they're already public in the shipped frontend bundle)
5. **Re-run `terraform apply`** (or, if App Runner is already stuck in `CREATE_FAILED` from step 2, `terraform apply -replace=aws_apprunner_service.frontend`) now that an image exists -- this creates the App Runner service for real.
6. **Verify before cutting over**: manually run each ECS task once (`aws ecs run-task --cluster used-cars-finder-cluster --task-definition used-cars-finder-scrape ...`, matching network config from `scheduler.tf`) and check CloudWatch Logs. Check the App Runner service URL (`terraform output apprunner_service_url`) loads correctly.
7. **Only after that's confirmed working**: disable the `schedule:` trigger in `.github/workflows/scraper.yml` and `.github/workflows/notify.yml` (keep `workflow_dispatch` in both as a manual fallback). Until you do this, both the old GitHub Actions cron *and* the new AWS schedule will run in parallel -- harmless (the scraper's upsert logic is idempotent) but redundant.

## Redeploying after this

Every push to `main` that touches `scraper/**` rebuilds+pushes the scraper image and registers new task definition revisions automatically; the very next scheduled run picks up the new image (EventBridge targets the task-definition *family*, not a pinned revision). Every push touching the frontend rebuilds+pushes that image, and App Runner auto-deploys it. Nothing about this Terraform config needs to change or be re-applied for routine code changes -- only for infrastructure changes (new secrets, schedule changes, scaling changes, etc).

## First deployment log (2026-07-20)

What actually happened standing this up for real, including every CLI command, kept here in case a future from-scratch deploy (new AWS account, new machine) hits the same things.

**1. Checked existing AWS setup.**
```bash
which aws terraform
ls -la ~/.aws/
aws sts get-caller-identity
aws configure get region
```
Found AWS CLI and existing credentials already configured (for an unrelated IAM user, `serverless-nodejs-api`), but no Terraform.

**2. Installed Terraform.** Homebrew's tap trust gating blocked the normal install path (`brew install terraform` and `brew tap hashicorp/tap` both failed) -- grabbed the binary directly from HashiCorp instead:
```bash
uname -m   # arm64
curl -sL https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_darwin_arm64.zip -o /tmp/terraform.zip
unzip -o /tmp/terraform.zip -d /tmp/terraform-bin
chmod +x /tmp/terraform-bin/terraform
cp /tmp/terraform-bin/terraform /opt/homebrew/bin/terraform   # user-writable, already on PATH
terraform version
```

**3. Validated the config before touching anything.**
```bash
cd terraform
terraform init
terraform validate
```

**4. Built `terraform.tfvars`** using values already on hand: `SUPABASE_URL`/`SUPABASE_SECRET_KEY`/`RESEND_API_KEY` from `scraper/.env`, the repo name from `git remote get-url origin`, and the account's own email for `alert_email`.

**5. First `terraform plan` attempt failed on permissions.**
```bash
terraform plan -out=tfplan
```
The existing `serverless-nodejs-api` credential couldn't even read VPC info (`ec2:DescribeVpcs` denied), and couldn't introspect its own policies either:
```bash
aws iam list-attached-user-policies --user-name serverless-nodejs-api   # AccessDenied
aws iam list-user-policies --user-name serverless-nodejs-api             # AccessDenied
aws iam list-groups-for-user --user-name serverless-nodejs-api           # AccessDenied
```
Clearly scoped for some other project. Got a new IAM user (`used-cars-finder-deploy`, `AdministratorAccess`) with a fresh access key instead.

**6. Added the new key as a separate AWS CLI profile** (not overwriting the existing `default`):
```bash
cat >> ~/.aws/credentials << 'EOF'
[used-cars-finder]
aws_access_key_id = ...
aws_secret_access_key = ...
EOF
aws sts get-caller-identity --profile used-cars-finder
```
Confirmed a different AWS account than `default`'s.

**7. Re-ran the plan -- clean.**
```bash
AWS_PROFILE=used-cars-finder terraform plan -out=tfplan
terraform show tfplan | grep "will be created" | sed 's/# //;s/ will be created//' | sort
```
34 resources, reviewed before applying.

**8. Applied -- 32 of 34 succeeded; App Runner failed exactly as the bootstrap note above describes.**
```bash
AWS_PROFILE=used-cars-finder terraform apply "tfplan"
```
`aws_apprunner_service.frontend` came back `CREATE_FAILED` (no image in ECR yet, and App Runner validates synchronously at creation unlike ECS task definitions).
```bash
terraform state list
aws apprunner list-services --region us-west-2
```

**9. Started Docker** (installed but the daemon wasn't running):
```bash
docker ps   # "Cannot connect to the Docker daemon"
open -a Docker
# polled `docker ps` every 10s until it responded
```

**10. Built and pushed the scraper image -- first build was the wrong architecture.**
```bash
terraform output
aws ecr get-login-password --region us-west-2 --profile used-cars-finder | docker login --username AWS --password-stdin 236553837104.dkr.ecr.us-west-2.amazonaws.com

cd ../scraper
docker build -t 236553837104.dkr.ecr.us-west-2.amazonaws.com/used-cars-finder-scraper:latest .
# built for arm64 (this Mac's native arch) by default -- wrong, Fargate task defs here default to X86_64

docker build --platform linux/amd64 -t 236553837104.dkr.ecr.us-west-2.amazonaws.com/used-cars-finder-scraper:latest .
docker push 236553837104.dkr.ecr.us-west-2.amazonaws.com/used-cars-finder-scraper:latest
```

**11. Built and pushed the frontend image**, with `NEXT_PUBLIC_*` as build args (Next.js inlines them at build time, not runtime) pulled from `.env.local`:
```bash
cd ..
docker build --platform linux/amd64 \
  --build-arg NEXT_PUBLIC_SUPABASE_URL="..." \
  --build-arg NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="..." \
  -t 236553837104.dkr.ecr.us-west-2.amazonaws.com/used-cars-finder-frontend:latest .
docker push 236553837104.dkr.ecr.us-west-2.amazonaws.com/used-cars-finder-frontend:latest
```

**12. Replaced the failed App Runner service now that an image existed.**
```bash
cd terraform
AWS_PROFILE=used-cars-finder terraform apply -replace=aws_apprunner_service.frontend -auto-approve
```
Succeeded this time (took ~4 minutes).

**13. Verified the frontend.**
```bash
curl -sI https://<apprunner-url>/
curl -s https://<apprunner-url>/ | grep -o '<title>[^<]*</title>'
aws apprunner describe-service --service-arn ... --query 'Service.{Status:Status,AutoDeploy:SourceConfiguration.AutoDeploymentsEnabled}'
```
`curl` alone didn't show real page content since this frontend fetches data client-side after hydration -- confirmed it actually worked by loading it in a real browser instead (real production data: sources/listings counts, live deal cards).

**14. GitHub repo variables** (`AWS_GITHUB_ACTIONS_ROLE_ARN`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`) were set by hand in the GitHub UI -- no `gh` CLI or token was available in this environment to script it.

**15. Manually triggered the scrape task to verify end-to-end** before trusting the schedule:
```bash
aws ec2 describe-subnets --filters "Name=default-for-az,Values=true" --query 'Subnets[0].SubnetId'
aws ec2 describe-security-groups --filters "Name=group-name,Values=used-cars-finder-scraper-tasks" --query 'SecurityGroups[0].GroupId'

aws ecs run-task \
  --cluster used-cars-finder-cluster \
  --task-definition used-cars-finder-scrape \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[...],securityGroups=[...],assignPublicIp=ENABLED}"

# polled every 15s:
aws ecs describe-tasks --cluster used-cars-finder-cluster --tasks <taskArn> --query 'tasks[0].lastStatus'
```
