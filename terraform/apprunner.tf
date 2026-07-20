# Runs the frontend's Dockerfile as a built image rather than pointing App
# Runner's native GitHub integration at the repo directly -- that path
# needs a one-time manual OAuth handshake in the console to authorize the
# GitHub connection, which can't be done from Terraform. Building via CI
# into ECR (same pattern as the scraper image) keeps the entire AWS side
# of this fully `terraform apply`-able with no console steps.
#
# NEXT_PUBLIC_* vars are NOT set here: Next.js inlines them into the
# client JS bundle at `next build` time, which already happened before
# this image was pushed -- setting them as App Runner runtime env vars
# here would be too late to have any effect. They're passed as Docker
# --build-arg values in the GitHub Actions workflow instead.
#
# Same bootstrapping note as ecs.tf: this references
# "${...repository_url}:latest", which must exist before the first
# `terraform apply` creates this service.

resource "aws_apprunner_service" "frontend" {
  service_name = "${var.project_name}-frontend"

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.apprunner_ecr_access.arn
    }
    # New image pushes to :latest auto-deploy -- no separate
    # `apprunner start-deployment` step needed in CI.
    auto_deployments_enabled = true

    image_repository {
      image_identifier      = "${aws_ecr_repository.frontend.repository_url}:latest"
      image_repository_type = "ECR"

      image_configuration {
        port = "3000"
      }
    }
  }

  instance_configuration {
    cpu    = "1024"
    memory = "2048"
  }

  health_check_configuration {
    protocol = "HTTP"
    path     = "/"
  }
}
