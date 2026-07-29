# ----------------------------------------------------
# AWS CloudFront CDN Distribution for EKS Frontend Website
# Routes all web traffic and WebSockets to EKS ALB
# ----------------------------------------------------

resource "aws_cloudfront_distribution" "website" {
  origin {
    domain_name = var.eks_ingress_dns == "" ? "placeholder.ingress.local" : var.eks_ingress_dns
    origin_id   = "EKS-ALB-Ingress"

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "http-only" # Ingress ALB currently listens on HTTP port 80
      origin_ssl_protocols     = ["TLSv1.2"]
    }
  }

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "SmartRetailX Production CDN for EKS Frontend Website and WebSockets"
  default_root_object = ""

  # Default cache behavior for EKS dynamic React application & API calls
  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "EKS-ALB-Ingress"

    # Forward all headers (host, user-agent, auth) and cookies to support WebSockets & auth sessions
    forwarded_values {
      query_string = true
      headers      = ["Host", "Origin", "User-Agent", "Authorization", "X-User-ID", "X-User-Role", "Sec-WebSocket-Key", "Sec-WebSocket-Version", "Sec-WebSocket-Extensions", "Sec-WebSocket-Protocol"]

      cookies {
        forward = "all"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    
    # Pass-through settings to prevent caching of dynamic application pages
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
  }

  # Geo-restrictions (none by default)
  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # Default CloudFront SSL certificate (*.cloudfront.net)
  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = {
    Name        = "smartretailx-cloudfront"
    Environment = var.environment
    Project     = var.project_name
  }
}
