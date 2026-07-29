# ----------------------------------------------------
# AWS S3 Module (Frontend Website Public Assets Bucket)
# ----------------------------------------------------

resource "aws_s3_bucket" "assets" {
  bucket        = "smartretailx-public-assets-${var.environment}"
  force_destroy = true

  tags = {
    Name        = "smartretailx-public-assets"
    Environment = var.environment
  }
}

# Enable Public Access Block rules (allow selective public reads)
resource "aws_s3_bucket_public_access_block" "public_rules" {
  bucket = aws_s3_bucket.assets.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# Bucket Policy enabling read access for website images
resource "aws_s3_bucket_policy" "public_policy" {
  depends_on = [aws_s3_bucket_public_access_block.public_rules]
  bucket     = aws_s3_bucket.assets.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.assets.arn}/*"
      }
    ]
  })
}
