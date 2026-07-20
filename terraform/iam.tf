locals {
  # ARN pointing at a task-definition *family* with no revision suffix --
  # ECS resolves this to whatever revision is currently ACTIVE. Used so
  # EventBridge Scheduler and its IAM policy always run the latest image
  # CI registers, without this Terraform config needing to change (or
  # re-apply) every time CI pushes a new revision.
  scrape_task_def_family_arn = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task-definition/${aws_ecs_task_definition.scrape.family}"
  notify_task_def_family_arn = "arn:aws:ecs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:task-definition/${aws_ecs_task_definition.notify.family}"
}

# --- ECS task execution role: pulls the image from ECR, writes logs to
# CloudWatch, reads the 3 secrets into the container's env. Shared by both
# the scrape and notify task definitions -- neither needs a separate task
# *role*, since the scraper code never calls any other AWS API itself. ---

resource "aws_iam_role" "ecs_task_execution" {
  name = "${var.project_name}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name = "${var.project_name}-read-secrets"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = "secretsmanager:GetSecretValue"
      Resource = [
        aws_secretsmanager_secret.supabase_url.arn,
        aws_secretsmanager_secret.supabase_secret_key.arn,
        aws_secretsmanager_secret.resend_api_key.arn,
      ]
    }]
  })
}

# --- EventBridge Scheduler execution role: allowed to RunTask only the
# two task-definition families in this one cluster. ---

resource "aws_iam_role" "scheduler_execution" {
  name = "${var.project_name}-scheduler-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler_run_task" {
  name = "${var.project_name}-run-ecs-task"
  role = aws_iam_role.scheduler_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecs:RunTask"
        Resource = ["${local.scrape_task_def_family_arn}:*", "${local.notify_task_def_family_arn}:*"]
        Condition = {
          ArnLike = { "ecs:cluster" = aws_ecs_cluster.main.arn }
        }
      },
      {
        # ECS needs to assume the task execution role on the scheduler's
        # behalf to actually launch the task.
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = [aws_iam_role.ecs_task_execution.arn]
      }
    ]
  })
}

# --- GitHub Actions OIDC: lets the deploy workflow assume a role without
# any long-lived AWS access keys stored as GitHub secrets. ---

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  # GitHub's OIDC provider TLS root CA thumbprint (rotates rarely; AWS's
  # own docs carry the current value if this ever needs updating).
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_actions" {
  name = "${var.project_name}-github-actions-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          # Restricted to pushes on one branch -- PRs and other branches
          # never get deploy credentials.
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/${var.github_branch}"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  name = "${var.project_name}-deploy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*" # this specific action does not support resource-level restriction
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:BatchGetImage",
        ]
        Resource = [aws_ecr_repository.scraper.arn, aws_ecr_repository.frontend.arn]
      },
      {
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition", "ecs:DescribeTaskDefinition"]
        Resource = "*" # RegisterTaskDefinition does not support resource-level restriction either
      },
      {
        # Needed because register-task-definition re-declares
        # executionRoleArn every time.
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = [aws_iam_role.ecs_task_execution.arn]
      },
    ]
  })
}

# --- App Runner's own role for pulling the frontend image from ECR
# (distinct from the GitHub Actions role -- this one is assumed by the
# App Runner service itself, not by CI). ---

resource "aws_iam_role" "apprunner_ecr_access" {
  name = "${var.project_name}-apprunner-ecr-access"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "apprunner_ecr_access" {
  role       = aws_iam_role.apprunner_ecr_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}
