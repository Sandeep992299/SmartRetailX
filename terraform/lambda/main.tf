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
      ENV                 = var.environment
      SES_RECIPIENT_EMAIL = "dissanayakesandeep@gmail.com"
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

# ============================================================
# Amazon EventBridge Integrations
# ============================================================

# 1. Event-Driven Rule for Custom Low-Stock Alert Pattern
resource "aws_cloudwatch_event_rule" "low_stock_rule" {
  name        = "${var.project_name}-low-stock-rule-${var.environment}"
  description = "Triggers Lambda when low stock events are published to EventBridge"

  event_pattern = jsonencode({
    source      = ["smartretailx.inventory"]
    detail-type = ["LowStockAlert"]
  })

  tags = {
    Environment = var.environment
  }
}

# Link custom EventBridge rule to Lambda function target
resource "aws_cloudwatch_event_target" "low_stock_target" {
  rule      = aws_cloudwatch_event_rule.low_stock_rule.name
  target_id = "SendToLambda"
  arn       = aws_lambda_function.notifier.arn
}

# Allow EventBridge custom rule to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_low_stock" {
  statement_id  = "AllowExecutionFromEventBridgeLowStock"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notifier.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.low_stock_rule.arn
}

# 2. Scheduled Rule (Cron Trigger for Daily System Health Report at 12:00 PM UTC)
resource "aws_cloudwatch_event_rule" "daily_report_rule" {
  name                = "${var.project_name}-daily-report-rule-${var.environment}"
  description         = "Triggers Lambda daily to send operational platform summary report"
  schedule_expression = "cron(0 12 * * ? *)"

  tags = {
    Environment = var.environment
  }
}

# Link scheduled EventBridge rule to Lambda function target
resource "aws_cloudwatch_event_target" "daily_report_target" {
  rule      = aws_cloudwatch_event_rule.daily_report_rule.name
  target_id = "SendDailyReportToLambda"
  arn       = aws_lambda_function.notifier.arn
}

# Allow EventBridge cron rule to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge_daily_report" {
  statement_id  = "AllowExecutionFromEventBridgeDailyReport"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notifier.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_report_rule.arn
}

# 3. Scheduled Rule (Cron Trigger for Daily Sales PDF Report at 11:59 PM UTC)
resource "aws_cloudwatch_event_rule" "daily_pdf_rule" {
  name                = "${var.project_name}-daily-pdf-rule-${var.environment}"
  description         = "Triggers Lambda at the end of each day to send sales summary PDF"
  schedule_expression = "cron(59 23 * * ? *)"

  tags = {
    Environment = var.environment
  }
}

# Link scheduled EventBridge PDF rule to Lambda target
resource "aws_cloudwatch_event_target" "daily_pdf_target" {
  rule      = aws_cloudwatch_event_rule.daily_pdf_rule.name
  target_id = "SendDailyPdfToLambda"
  arn       = aws_lambda_function.notifier.arn
}

# Allow EventBridge cron rule to invoke Lambda for PDF reports
resource "aws_lambda_permission" "allow_eventbridge_daily_pdf" {
  statement_id  = "AllowExecutionFromEventBridgeDailyPdf"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notifier.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_pdf_rule.arn
}
