# ----------------------------------------------------
# AWS CloudFront CDN Distribution for EKS Frontend Website & Assets
# Routes all web traffic and WebSockets to EKS ALB, and routes assets to S3
# ----------------------------------------------------

resource "aws_cloudfront_distribution" "website" {
  # Origin 1: EKS ALB Ingress
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

  # Origin 2: S3 Public Assets Bucket
  origin {
    domain_name = var.s3_bucket_domain_name
    origin_id   = "S3-Assets-Bucket"
  }

  enabled             = true
  is_ipv6_enabled     = true
  comment             = "SmartRetailX Production CDN for EKS Frontend Website and WebSockets"
  default_root_object = ""

  # Default cache behavior: routes to EKS ALB (serving React app & API Gateway)
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
    
    # Pass-through settings (no cache) since EKS serves dynamic code and routing
    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 0
  }

  # Cache behavior for static images (routed to S3 Assets Bucket)
  ordered_cache_behavior {
    path_pattern     = "/images/*"
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-Assets-Bucket"

    forwarded_values {
      query_string = false
      headers      = ["Origin", "Access-Control-Request-Headers", "Access-Control-Request-Method"]

      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    min_ttl                = 0
    default_ttl            = 86400    # Cache images for 1 day by default
    max_ttl                = 31536000 # Max 1 year
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
