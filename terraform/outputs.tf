output "vpc_id" {
  description = "Created VPC Identifier"
  value       = module.vpc.vpc_id
}

output "eks_cluster_endpoint" {
  description = "EKS API Control Plane Server Address"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_name" {
  description = "EKS Cluster Name"
  value       = module.eks.cluster_name
}

output "rds_endpoint" {
  description = "PostgreSQL Payments RDS Database connection address"
  value       = module.rds.db_endpoint
}

output "redis_primary_endpoint" {
  description = "Redis ElastiCache Primary cluster node Address"
  value       = module.elasticache.primary_endpoint
}

output "msk_bootstrap_brokers" {
  description = "MSK Managed Kafka connection broker nodes list"
  value       = module.msk.bootstrap_brokers
  sensitive   = true
}

output "notification_lambda_arn" {
  description = "Notification Lambda resource identifier"
  value       = module.lambda.lambda_arn
}

output "ecr_repository_urls" {
  description = "AWS Elastic Container Registry URLs for microservices hosting"
  value       = module.ecr.ecr_repository_urls
}

output "api_gateway_endpoint" {
  description = "Managed AWS API Gateway HTTP Endpoint URL for public requests"
  value       = module.apigateway.api_gateway_endpoint
}

output "cloudfront_domain_name" {
  description = "The public domain URL of the CloudFront CDN distribution"
  value       = "cloudfront-disabled-unverified-account"
}
