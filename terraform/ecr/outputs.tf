output "ecr_repository_urls" {
  description = "Map of microservice identifiers to their ECR repository registry URLs"
  value       = { for k, v in aws_ecr_repository.services : k => v.repository_url }
}
