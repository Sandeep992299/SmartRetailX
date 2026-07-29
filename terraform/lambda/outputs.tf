output "lambda_arn" {
  value = aws_lambda_function.notifier.arn
}

output "sqs_queue_url" {
  value = aws_sqs_queue.notification_queue.id
}

output "sqs_queue_arn" {
  value = aws_sqs_queue.notification_queue.arn
}
