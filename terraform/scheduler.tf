resource "aws_scheduler_schedule" "scrape" {
  name       = "${var.project_name}-scrape"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.scrape_schedule_expression
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler_execution.arn

    ecs_parameters {
      # Family-only ARN (no revision) -- always resolves to the latest
      # ACTIVE revision, see iam.tf.
      task_definition_arn = local.scrape_task_def_family_arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = data.aws_subnets.default.ids
        security_groups  = [aws_security_group.scraper_tasks.id]
        assign_public_ip = true
      }
    }
  }
}

resource "aws_scheduler_schedule" "notify" {
  name       = "${var.project_name}-notify"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.notify_schedule_expression
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler_execution.arn

    ecs_parameters {
      task_definition_arn = local.notify_task_def_family_arn
      launch_type         = "FARGATE"

      network_configuration {
        subnets          = data.aws_subnets.default.ids
        security_groups  = [aws_security_group.scraper_tasks.id]
        assign_public_ip = true
      }
    }
  }
}
