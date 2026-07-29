output "cloudfront_domain_name" {
  description = "The domain name of the CloudFront CDN distribution"
  value       = aws_cloudfront_distribution.website.domain_name
}
