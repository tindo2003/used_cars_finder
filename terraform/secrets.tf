# Mirrors scraper/.env locally and the GitHub Actions secrets scraper.yml
# / notify.yml already use -- same three values, just readable by ECS
# tasks instead of a GitHub-hosted runner. os.getenv(...) in the Python
# code doesn't change; these are injected as container env vars via the
# task definitions' `secrets` block (see ecs.tf).

resource "aws_secretsmanager_secret" "supabase_url" {
  name = "${var.project_name}/supabase-url"
}

resource "aws_secretsmanager_secret_version" "supabase_url" {
  secret_id     = aws_secretsmanager_secret.supabase_url.id
  secret_string = var.supabase_url
}

resource "aws_secretsmanager_secret" "supabase_secret_key" {
  name = "${var.project_name}/supabase-secret-key"
}

resource "aws_secretsmanager_secret_version" "supabase_secret_key" {
  secret_id     = aws_secretsmanager_secret.supabase_secret_key.id
  secret_string = var.supabase_secret_key
}

resource "aws_secretsmanager_secret" "resend_api_key" {
  name = "${var.project_name}/resend-api-key"
}

resource "aws_secretsmanager_secret_version" "resend_api_key" {
  secret_id     = aws_secretsmanager_secret.resend_api_key.id
  secret_string = var.resend_api_key
}
