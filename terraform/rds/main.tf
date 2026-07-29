# ----------------------------------------------------
# RDS PostgreSQL Module (Payments Database)
# ----------------------------------------------------

resource "aws_db_subnet_group" "rds" {
  name        = "${var.environment}-rds-subnet-group"
  subnet_ids  = var.private_subnet_ids
  description = "RDS private database subnet group"

  tags = {
    Name        = "${var.environment}-rds-subnet-group"
    Environment = var.environment
  }
}

resource "aws_security_group" "rds" {
  name        = "${var.environment}-rds-sg"
  description = "Allow inbound PostgreSQL access from EKS nodes"
  vpc_id      = var.vpc_id

  ingress {
    description     = "PostgreSQL connectivity from EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.allowed_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.environment}-rds-sg"
    Environment = var.environment
  }
}

resource "aws_db_instance" "postgres" {
  identifier             = "${var.environment}-payments-db"
  allocated_storage      = 20
  max_allocated_storage  = 100
  db_name                = var.db_name
  engine                 = "postgres"
  engine_version         = "16.3"
  instance_class         = "db.t3.micro"
  username               = var.db_user
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.rds.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = true
  multi_az               = false # Set to true in production for multi-AZ high availability

  tags = {
    Name        = "${var.environment}-payments-db"
    Environment = var.environment
  }
}
