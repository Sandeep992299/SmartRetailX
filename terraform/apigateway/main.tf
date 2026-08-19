# ============================================================
# SmartRetailX — AWS API Gateway v2 (HTTP API) Module Config
# ============================================================

locals {
  nlb_host = "10.0.11.208" # Replace with NLB DNS after load balancer limit raised
  
  # Service base URIs on EKS NodePorts
  user_base      = "http://${local.nlb_host}:30081"
  product_base   = "http://${local.nlb_host}:30082"
  order_base     = "http://${local.nlb_host}:30083"
  payment_base   = "http://${local.nlb_host}:30084"
  inventory_base = "http://${local.nlb_host}:30085"
}

# ------------------------------------------------------------
# CloudWatch Log Group for API Gateway Access Logs
# ------------------------------------------------------------
resource "aws_cloudwatch_log_group" "apigw_logs" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}"
  retention_in_days = 30

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}

# ------------------------------------------------------------
# HTTP API Gateway Instance
# ------------------------------------------------------------
resource "aws_apigatewayv2_api" "main" {
  name          = "${var.project_name}-api-${var.environment}"
  protocol_type = "HTTP"
  description   = "SmartRetailX Managed HTTP API Gateway — Routes microservice traffic with versioning, CORS, throttling, and CloudWatch access logging."

  cors_configuration {
    allow_headers     = ["Content-Type", "Authorization", "X-Request-ID", "X-Api-Key", "X-User-ID", "X-User-Role"]
    allow_methods     = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    allow_origins     = ["*"]
    expose_headers    = ["X-Request-ID", "X-Total-Count"]
    max_age           = 3600
    allow_credentials = false
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "Terraform"
    Version     = "v1"
  }
}

# ------------------------------------------------------------
# VPC Link Security Group
# ------------------------------------------------------------
resource "aws_security_group" "apigw_vpc_link" {
  name        = "${var.project_name}-apigw-vpc-link-sg"
  description = "Controls egress from API Gateway v2 VPC Link into private EKS subnets"
  vpc_id      = var.vpc_id

  egress {
    description = "Allow all outbound to EKS NodePort range"
    from_port   = 30000
    to_port     = 32767
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    description = "Allow HTTPS outbound"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-apigw-vpc-link-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ------------------------------------------------------------
# VPC Link — bridges API Gateway to private EKS subnets
# ------------------------------------------------------------
resource "aws_apigatewayv2_vpc_link" "main" {
  name               = "${var.project_name}-vpc-link-${var.environment}"
  security_group_ids = [aws_security_group.apigw_vpc_link.id]
  subnet_ids         = var.private_subnet_ids

  tags = {
    Name        = "${var.project_name}-vpc-link"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ============================================================
# NOTE: NLB disabled until AWS account load balancer limit raised.
# ============================================================
# resource "aws_lb" "eks_internal" {
#   name               = "${var.project_name}-eks-internal-nlb"
#   internal           = true
#   load_balancer_type = "network"
#   subnets            = var.private_subnet_ids
#   enable_cross_zone_load_balancing = true
#   tags = { Environment = var.environment, Project = var.project_name }
# }

# ============================================================
# USER SERVICE — Port 30081
# ============================================================

resource "aws_apigatewayv2_integration" "user_signup" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "POST"
  integration_uri        = "${local.user_base}/users/signup"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "user_signup" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /v1/users/signup"
  target    = "integrations/${aws_apigatewayv2_integration.user_signup.id}"
}

resource "aws_apigatewayv2_integration" "user_login" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "POST"
  integration_uri        = "${local.user_base}/users/login"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "user_login" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /v1/users/login"
  target    = "integrations/${aws_apigatewayv2_integration.user_login.id}"
}

resource "aws_apigatewayv2_integration" "user_me" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.user_base}/users/me"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "user_me" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/users/me"
  target    = "integrations/${aws_apigatewayv2_integration.user_me.id}"
}

resource "aws_apigatewayv2_integration" "users_list" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.user_base}/users"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "users_list" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/users"
  target    = "integrations/${aws_apigatewayv2_integration.users_list.id}"
}

resource "aws_apigatewayv2_integration" "user_health" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.user_base}/users/healthz"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 10000
}
resource "aws_apigatewayv2_route" "user_health" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/users/healthz"
  target    = "integrations/${aws_apigatewayv2_integration.user_health.id}"
}

# ============================================================
# PRODUCT SERVICE — Port 30082
# ============================================================

resource "aws_apigatewayv2_integration" "products_list" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.product_base}/products"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "products_list" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/products"
  target    = "integrations/${aws_apigatewayv2_integration.products_list.id}"
}

resource "aws_apigatewayv2_integration" "product_get" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.product_base}/products/{product_id}"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "product_get" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/products/{product_id}"
  target    = "integrations/${aws_apigatewayv2_integration.product_get.id}"
}

resource "aws_apigatewayv2_integration" "product_create" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "POST"
  integration_uri        = "${local.product_base}/products"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "product_create" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /v1/products"
  target    = "integrations/${aws_apigatewayv2_integration.product_create.id}"
}

resource "aws_apigatewayv2_integration" "product_update" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "PUT"
  integration_uri        = "${local.product_base}/products/{product_id}"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "product_update" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "PUT /v1/products/{product_id}"
  target    = "integrations/${aws_apigatewayv2_integration.product_update.id}"
}

resource "aws_apigatewayv2_integration" "product_delete" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "DELETE"
  integration_uri        = "${local.product_base}/products/{product_id}"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "product_delete" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "DELETE /v1/products/{product_id}"
  target    = "integrations/${aws_apigatewayv2_integration.product_delete.id}"
}

resource "aws_apigatewayv2_integration" "product_health" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.product_base}/products/healthz"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 10000
}
resource "aws_apigatewayv2_route" "product_health" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/products/healthz"
  target    = "integrations/${aws_apigatewayv2_integration.product_health.id}"
}

# ============================================================
# ORDER SERVICE — Port 30083
# ============================================================

resource "aws_apigatewayv2_integration" "order_create" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "POST"
  integration_uri        = "${local.order_base}/orders"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "order_create" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "POST /v1/orders"
  target    = "integrations/${aws_apigatewayv2_integration.order_create.id}"
}

resource "aws_apigatewayv2_integration" "orders_list" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.order_base}/orders"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "orders_list" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/orders"
  target    = "integrations/${aws_apigatewayv2_integration.orders_list.id}"
}

resource "aws_apigatewayv2_integration" "order_get" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.order_base}/orders/{order_id}"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "order_get" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/orders/{order_id}"
  target    = "integrations/${aws_apigatewayv2_integration.order_get.id}"
}

resource "aws_apigatewayv2_integration" "order_status" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "PUT"
  integration_uri        = "${local.order_base}/orders/{order_id}/status"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "order_status" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "PUT /v1/orders/{order_id}/status"
  target    = "integrations/${aws_apigatewayv2_integration.order_status.id}"
}

resource "aws_apigatewayv2_integration" "order_health" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.order_base}/orders/healthz"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 10000
}
resource "aws_apigatewayv2_route" "order_health" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/orders/healthz"
  target    = "integrations/${aws_apigatewayv2_integration.order_health.id}"
}

# ============================================================
# PAYMENT SERVICE — Port 30084
# ============================================================

resource "aws_apigatewayv2_integration" "payment_transactions" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.payment_base}/payments/transactions"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "payment_transactions" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/payments/transactions"
  target    = "integrations/${aws_apigatewayv2_integration.payment_transactions.id}"
}

resource "aws_apigatewayv2_integration" "payment_health" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.payment_base}/payments/healthz"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 10000
}
resource "aws_apigatewayv2_route" "payment_health" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/payments/healthz"
  target    = "integrations/${aws_apigatewayv2_integration.payment_health.id}"
}

# ============================================================
# INVENTORY SERVICE — Port 30085
# ============================================================

resource "aws_apigatewayv2_integration" "inventory_list" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.inventory_base}/inventory"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "inventory_list" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/inventory"
  target    = "integrations/${aws_apigatewayv2_integration.inventory_list.id}"
}

resource "aws_apigatewayv2_integration" "inventory_get" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.inventory_base}/inventory/{product_id}"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "inventory_get" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/inventory/{product_id}"
  target    = "integrations/${aws_apigatewayv2_integration.inventory_get.id}"
}

resource "aws_apigatewayv2_integration" "inventory_update" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "PUT"
  integration_uri        = "${local.inventory_base}/inventory/{product_id}"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "inventory_update" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "PUT /v1/inventory/{product_id}"
  target    = "integrations/${aws_apigatewayv2_integration.inventory_update.id}"
}

resource "aws_apigatewayv2_integration" "inventory_health" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "GET"
  integration_uri        = "${local.inventory_base}/inventory/healthz"
  connection_type        = "INTERNET"
  # connection_id          = aws_apigatewayv2_vpc_link.main.id
  payload_format_version = "1.0"
  timeout_milliseconds   = 10000
}
resource "aws_apigatewayv2_route" "inventory_health" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /v1/inventory/healthz"
  target    = "integrations/${aws_apigatewayv2_integration.inventory_health.id}"
}

# ============================================================
# Global health check route
# ============================================================
resource "aws_apigatewayv2_route" "global_health" {
  api_id    = aws_apigatewayv2_api.main.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.user_health.id}"
}

# ============================================================
# v1 Stage — throttled, logged, with stage variables
# ============================================================
resource "aws_apigatewayv2_stage" "v1" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "v1"
  auto_deploy = true
  description = "SmartRetailX v1 — production stage with per-service throttling and CloudWatch access logging."

  depends_on = [
    aws_apigatewayv2_route.payment_transactions
  ]

  default_route_settings {
    throttling_burst_limit   = 500
    throttling_rate_limit    = 1000
    detailed_metrics_enabled = true
    logging_level            = "INFO"
    data_trace_enabled       = false
  }

  # Tighter throttling on payment routes
  route_settings {
    route_key                = "GET /v1/payments/transactions"
    throttling_burst_limit   = 100
    throttling_rate_limit    = 200
    detailed_metrics_enabled = true
  }

  stage_variables = {
    environment = var.environment
    project     = var.project_name
    api_version = "v1"
    region      = var.aws_region
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
    Stage       = "v1"
  }
}
