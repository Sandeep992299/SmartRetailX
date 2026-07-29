output "api_gateway_endpoint" {
  description = "The HTTP stage invocation URL of the API Gateway v1 deployment"
  value       = aws_apigatewayv2_stage.v1.invoke_url
}
