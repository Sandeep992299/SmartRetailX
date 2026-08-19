# ----------------------------------------------------
# ECR Module (Amazon Elastic Container Registry Repositories)
# ----------------------------------------------------

resource "aws_ecr_repository" "services" {
  for_each             = toset(["user-service", "product-service", "order-service", "payment-service", "inventory-service", "notification-service", "frontend", "api-gateway"])
  name                 = "${var.project_name}-${each.value}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_ecr_lifecycle_policy" "cleanup" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = <<EOF
{
    "rules": [
        {
            "rulePriority": 1,
            "description": "Keep only the last 10 images to save storage space",
            "selection": {
                "tagStatus": "any",
                "countType": "imageCountMoreThan",
                "countNumber": 10
            },
            "action": {
                "type": "expire"
            }
        }
    ]
}
EOF
}
