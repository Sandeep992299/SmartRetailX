# ----------------------------------------------------
# Lambda Module (Serverless Event-Driven Notifications)
# ----------------------------------------------------

# SQS Queue that triggers the Lambda
resource "aws_sqs_queue" "notification_queue" {
  name                      = "${var.project_name}-notification-queue-${var.environment}"
  delay_seconds             = 0
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10 # Long polling

  tags = {
    Environment = var.environment
  }
}

# IAM Role for Notification Lambda Function
resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-lambda-execution-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Attach basic execution policies (CloudWatch logs, VPC integration, SQS reading)
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.lambda.name
}

resource "aws_iam_role_policy_attachment" "lambda_sqs" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaSQSQueueExecutionRole"
  role       = aws_iam_role.lambda.name
}

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
  role       = aws_iam_role.lambda.name
}

# Mock source code zip for terraform verification
data "archive_file" "dummy" {
  type        = "zip"
  output_path = "${path.module}/dummy_payload.zip"
  
  source {
    content  = "def lambda_handler(event, context): return {'statusCode': 200}"
    filename = "main.py"
  }
}

# Security Group for Lambda in VPC
resource "aws_security_group" "lambda" {
  name        = "${var.project_name}-lambda-sg-${var.environment}"
  description = "Security group for serverless notification function"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-lambda-sg"
    Environment = var.environment
  }
}

# Notification Lambda Function
resource "aws_lambda_function" "notifier" {
  filename      = data.archive_file.dummy.output_path
  function_name = "${var.project_name}-notifier-${var.environment}"
  role          = aws_iam_role.lambda.arn
  handler       = "main.lambda_handler"
  runtime       = "python3.10"
  timeout       = 30

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      ENV = var.environment
    }
  }

  tags = {
    Environment = var.environment
  }
}

# SQS event source trigger configuration (Tasks 4 Event-Driven Lambda)
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.notification_queue.arn
  function_name    = aws_lambda_function.notifier.arn
  batch_size       = 10
  enabled          = true
}
