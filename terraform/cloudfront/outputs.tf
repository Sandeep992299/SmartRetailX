output "cloudfront_domain_name" {
  description = "The domain name of the CloudFront CDN distribution"
  value       = aws_cloudfront_distribution.website.domain_name
}

output "cloudfront_hosted_zone_id" {
  description = "The hosted zone ID of the CloudFront CDN distribution"
  value       = aws_cloudfront_distribution.website.hosted_zone_id
}
