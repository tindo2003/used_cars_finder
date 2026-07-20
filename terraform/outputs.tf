output "ecr_scraper_repository_url" {
  value = aws_ecr_repository.scraper.repository_url
}

output "ecr_frontend_repository_url" {
  value = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "apprunner_service_url" {
  description = "The live frontend URL once the first image has been pushed and deployed"
  value       = aws_apprunner_service.frontend.service_url
}

output "github_actions_role_arn" {
  description = "Paste into the GitHub Actions workflow's role-to-assume input / repo variable"
  value       = aws_iam_role.github_actions.arn
}
