variable "environment" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "eks_cluster_name" {
  type = string
}

variable "node_instance_type" {
  type = string
}

variable "console_iam_arns" {
  description = "List of IAM User/Role ARNs that should be granted cluster-admin access to the EKS cluster"
  type        = list(string)
  default     = []
}
