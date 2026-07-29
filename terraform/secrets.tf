# ============================================================
# SmartRetailX — AWS Secrets Manager Configuration
# ============================================================

# Secrets Manager Container
resource "aws_secretsmanager_secret" "platform_secrets" {
  name                    = "${var.project_name}-credentials-${var.environment}"
  description             = "Database passwords, JWT secrets, Redis passwords, Kafka SASL credentials, and SMTP mail auth."
  recovery_window_in_days = 7

  tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "Terraform"
  }
}

# Initial seed values for secrets (to be overridden manually in production)
resource "aws_secretsmanager_secret_version" "platform_secrets_init" {
  secret_id = aws_secretsmanager_secret.platform_secrets.id
  secret_string = jsonencode({
    JWT_SECRET       = "smartretailx-super-secret-key-123456"
    DB_USER          = "sr_admin"
    DB_PASSWORD      = "SecurePgPassword123!"
    REDIS_PASSWORD   = "SecureRedisPassword123!"
    KAFKA_USER       = "kafka_app_client"
    KAFKA_PASSWORD   = "SecureKafkaPassword123!"
    SMTP_USERNAME    = "smtp_user"
    SMTP_PASSWORD    = "SecureSmtpPassword123!"
  })
}

# IAM Policy allowing EKS nodes to read/decrypt the secrets
resource "aws_iam_policy" "secrets_read_policy" {
  name        = "${var.project_name}-secrets-read-policy-${var.environment}"
  description = "Allows EKS worker node pods to retrieve and decrypt credentials from AWS Secrets Manager using KMS"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [aws_secretsmanager_secret.platform_secrets.arn]
      }
    ]
  })
}

# Attach IAM Policy to the EKS worker nodes role
resource "aws_iam_role_policy_attachment" "eks_secrets_attach" {
  policy_arn = aws_iam_policy.secrets_read_policy.arn
  role       = module.eks.node_role_name
}
