# ----------------------------------------------------
# SmartRetailX Root Terraform Configuration
# ----------------------------------------------------

terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = "aquasense"
}

# 1. VPC Module (Networking)
module "vpc" {
  source               = "./vpc"
  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

# 2. EKS Module (Kubernetes Container Management)
module "eks" {
  source             = "./eks"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  eks_cluster_name   = "${var.project_name}-eks-${var.environment}"
  node_instance_type = var.eks_node_instance_type
  console_iam_arns   = [
    "arn:aws:iam::595529181954:root"
  ]
}

# 3. RDS PostgreSQL Module (Payments Database)
module "rds" {
  source             = "./rds"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  db_name            = "smartretailx_payments"
  db_user            = var.db_user
  db_password        = var.db_password
  allowed_security_group_id = module.eks.node_security_group_id
}

# 4. ElastiCache Redis Module (Catalog Cache & Rate Limit Store)
module "elasticache" {
  source             = "./elasticache"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  allowed_security_group_id = module.eks.node_security_group_id
}

# 5. MSK Kafka Module (Event Broker Hub)
module "msk" {
  source             = "./msk"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  allowed_security_group_id = module.eks.node_security_group_id
}

# 6. Lambda Module (Event-Driven Notification Lambda triggered by SQS)
module "lambda" {
  source            = "./lambda"
  environment       = var.environment
  project_name      = var.project_name
  vpc_id            = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
}

# 7. DocumentDB Module (MongoDB-Compatible Store for non-payment microservices)
module "documentdb" {
  source             = "./documentdb"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  allowed_security_group_id = module.eks.node_security_group_id
}

# 8. S3 Module (Frontend Website Public Assets Bucket)
module "s3" {
  source      = "./s3"
  environment = var.environment
}

# 9. ECR Module (Amazon Elastic Container Registry Repositories)
module "ecr" {
  source       = "./ecr"
  environment  = var.environment
  project_name = var.project_name
}

# 10. API Gateway Module (Managed API Gateway v2 HTTP API)
module "apigateway" {
  source             = "./apigateway"
  environment        = var.environment
  project_name       = var.project_name
  aws_region         = var.aws_region
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
}

# 11. CloudFront Module (CDN distribution for EKS Ingress)
module "cloudfront" {
  source                = "./cloudfront"
  environment           = var.environment
  project_name          = var.project_name
  eks_ingress_dns       = var.eks_ingress_dns
  s3_bucket_domain_name = module.s3.bucket_regional_domain_name
}

