resource "aws_ecs_cluster" "main" {
  name = "${var.project_name}-cluster"
}

resource "aws_cloudwatch_log_group" "scrape" {
  name              = "/ecs/${var.project_name}/scrape"
  retention_in_days = 30
}

resource "aws_cloudwatch_log_group" "notify" {
  name              = "/ecs/${var.project_name}/notify"
  retention_in_days = 30
}

# NOTE on bootstrapping: both task definitions below reference
# "${...repository_url}:latest", which won't exist until the GitHub
# Actions deploy workflow runs at least once and pushes an image. `terraform
# apply` will still succeed (ECS doesn't validate the image at
# registration time) -- the scheduled tasks just won't run successfully
# until that first image push happens. Push once manually or via CI
# before relying on the first scheduled run.
#
# `ignore_changes` on container_definitions is deliberate: after the
# initial apply, CI registers new revisions directly via `aws ecs
# register-task-definition` on every deploy (see
# .github/workflows/deploy.yml), and EventBridge always targets the
# latest ACTIVE revision by family name (see iam.tf's
# scrape_task_def_family_arn). Terraform re-registering its own
# (stale-image-tag) revision on every apply would fight that and
# undo whatever CI just shipped.

resource "aws_ecs_task_definition" "scrape" {
  family                   = "${var.project_name}-scrape"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([
    {
      name      = "scrape"
      image     = "${aws_ecr_repository.scraper.repository_url}:latest"
      essential = true
      command   = ["main.py"]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.scrape.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "scrape"
        }
      }
      secrets = [
        { name = "SUPABASE_URL", valueFrom = aws_secretsmanager_secret.supabase_url.arn },
        { name = "SUPABASE_SECRET_KEY", valueFrom = aws_secretsmanager_secret.supabase_secret_key.arn },
      ]
    }
  ])

  lifecycle {
    ignore_changes = [container_definitions]
  }
}

resource "aws_ecs_task_definition" "notify" {
  family                   = "${var.project_name}-notify"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([
    {
      name      = "notify"
      image     = "${aws_ecr_repository.scraper.repository_url}:latest"
      essential = true
      command   = ["notify.py"]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.notify.name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "notify"
        }
      }
      secrets = [
        { name = "SUPABASE_URL", valueFrom = aws_secretsmanager_secret.supabase_url.arn },
        { name = "SUPABASE_SECRET_KEY", valueFrom = aws_secretsmanager_secret.supabase_secret_key.arn },
        { name = "RESEND_API_KEY", valueFrom = aws_secretsmanager_secret.resend_api_key.arn },
      ]
    }
  ])

  lifecycle {
    ignore_changes = [container_definitions]
  }
}
