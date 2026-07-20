variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-west-2"
}

variable "project_name" {
  description = "Prefix used for naming every resource this config creates"
  type        = string
  default     = "used-cars-finder"
}

variable "github_repo" {
  description = "GitHub \"owner/repo\" allowed to assume the CI deploy role via OIDC, e.g. \"tindo/used_cars_finder\""
  type        = string
}

variable "github_branch" {
  description = "Branch allowed to assume the CI deploy role (pushes from other branches/PRs are not trusted with deploy credentials)"
  type        = string
  default     = "main"
}

variable "supabase_url" {
  description = "Supabase project URL -- same value as scraper/.env's SUPABASE_URL"
  type        = string
  sensitive   = true
}

variable "supabase_secret_key" {
  description = "Supabase service-role key -- same value as scraper/.env's SUPABASE_SECRET_KEY"
  type        = string
  sensitive   = true
}

variable "resend_api_key" {
  description = "Resend API key used by notify.py to send digest emails"
  type        = string
  sensitive   = true
}

variable "alert_email" {
  description = "Email address to notify when a scrape or notify Fargate task fails"
  type        = string
}

variable "scrape_schedule_expression" {
  description = "EventBridge Scheduler cron for the scrape task -- mirrors scraper.yml's existing */15 cron"
  type        = string
  default     = "cron(*/15 * * * ? *)"
}

variable "notify_schedule_expression" {
  description = "EventBridge Scheduler cron for the notify task -- mirrors notify.yml's existing 15:00 UTC / 8am Pacific cron"
  type        = string
  default     = "cron(0 15 * * ? *)"
}
