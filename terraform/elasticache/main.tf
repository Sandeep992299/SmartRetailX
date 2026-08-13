# ----------------------------------------------------
# ElastiCache Redis Module (Catalog Cache / Rate Limiter)
# ----------------------------------------------------

resource "aws_elasticache_subnet_group" "redis" {
  name        = "${var.environment}-redis-subnet-group"
  subnet_ids  = var.private_subnet_ids
  description = "Redis private elasticache subnet group"
}

resource "aws_security_group" "redis" {
  name        = "${var.environment}-redis-sg"
  description = "Allow Redis inbound access from EKS nodes"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Redis port 6379 connectivity"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.allowed_security_group_id]
    cidr_blocks     = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.environment}-redis-sg"
    Environment = var.environment
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id          = "${var.environment}-redis-cluster"
  description                   = "SmartRetailX Redis cache replication group"
  node_type                     = "cache.t3.micro"
  num_cache_clusters            = 1
  parameter_group_name          = "default.redis7"
  port                          = 6379
  subnet_group_name             = aws_elasticache_subnet_group.redis.name
  security_group_ids            = [aws_security_group.redis.id]
  automatic_failover_enabled    = false

  tags = {
    Name        = "${var.environment}-redis-cluster"
    Environment = var.environment
  }
}
