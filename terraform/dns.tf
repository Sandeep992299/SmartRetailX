# ============================================================
# SmartRetailX — Route 53 DNS Configuration
# ============================================================

# Primary Domain Hosted Zone
resource "aws_route53_zone" "primary" {
  name          = "smartretailx.internal"
  force_destroy = true

  tags = {
    Name        = "smartretailx-dns-zone"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Route 53 Health Check for the Primary active region
resource "aws_route53_health_check" "primary_region" {
  fqdn              = "app-primary.smartretailx.internal"
  port              = 80
  type              = "HTTP"
  resource_path     = "/healthz"
  failure_threshold = "3"
  request_interval  = "30"

  tags = {
    Name        = "primary-london-health-check"
    Environment = var.environment
    Project     = var.project_name
  }
}

# Primary DNS Record (Active) routing to CloudFront distribution
resource "aws_route53_record" "primary_cdn" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = "app.smartretailx.internal"
  type    = "A"

  alias {
    name                   = module.cloudfront.cloudfront_domain_name
    zone_id                = module.cloudfront.cloudfront_hosted_zone_id
    evaluate_target_health = true
  }

  set_identifier = "primary-london"
  failover_routing_policy {
    type = "PRIMARY"
  }

  health_check_id = aws_route53_health_check.primary_region.id
}

# Standby DNS Record (Passive) routing to secondary/failover region ALB
resource "aws_route53_record" "secondary_cdn" {
  zone_id = aws_route53_zone.primary.zone_id
  name    = "app.smartretailx.internal"
  type    = "A"

  # Mock IP representation of Frankfurt secondary ingress node endpoint
  ttl     = 60
  records = ["10.1.10.50"] 

  set_identifier = "secondary-frankfurt"
  failover_routing_policy {
    type = "SECONDARY"
  }
}
