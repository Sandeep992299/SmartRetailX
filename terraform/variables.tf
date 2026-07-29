variable "aws_region" {
  description = "AWS Target Deployment Region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name tag value"
  type        = string
  default     = "smartretailx"
}

variable "environment" {
  description = "Deployment Stage Environment (e.g. dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "vpc_cidr" {
  description = "IPv4 CIDR block allocation for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Target Availability Zones for HA deployments"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR range bounds for ingress public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR range bounds for private resource subnets"
  type        = list(string)
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "eks_node_instance_type" {
  description = "AWS EC2 Instance profile type for EKS worker nodes"
  type        = string
  default     = "t3.medium"
}

variable "db_user" {
  description = "Admin username for PostgreSQL Payments RDS Instance"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Admin password credentials for Payments RDS Database"
  type        = string
  sensitive   = true
  default     = "SuperSecurePass123!"
}

variable "eks_ingress_dns" {
  description = "DNS endpoint of the EKS ALB Ingress load balancer (leave empty for initial run)"
  type        = string
  default     = ""
}
