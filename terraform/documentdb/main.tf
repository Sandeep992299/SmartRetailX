# ----------------------------------------------------
# AWS DocumentDB Module (MongoDB-Compatible Store)
# ----------------------------------------------------

resource "aws_docdb_subnet_group" "docdb" {
  name       = "${var.environment}-docdb-subnet-group"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "docdb" {
  name        = "${var.environment}-docdb-sg"
  description = "Allow inbound DocumentDB traffic from EKS node group"
  vpc_id      = var.vpc_id

  ingress {
    description     = "DocumentDB MongoDB standard port"
    from_port       = 27017
    to_port         = 27017
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
    Name        = "${var.environment}-docdb-sg"
    Environment = var.environment
  }
}

resource "aws_docdb_cluster" "docdb" {
  cluster_identifier      = "${var.environment}-docdb-cluster"
  engine                  = "docdb"
  master_username         = var.master_username
  master_password         = var.master_password
  backup_retention_period = 5
  preferred_backup_window = "07:00-09:00"
  skip_final_snapshot     = true
  db_subnet_group_name    = aws_docdb_subnet_group.docdb.name
  vpc_security_group_ids  = [aws_security_group.docdb.id]
}

resource "aws_docdb_cluster_instance" "cluster_instances" {
  count              = 1
  identifier         = "${var.environment}-docdb-instance-${count.index}"
  cluster_identifier = aws_docdb_cluster.docdb.id
  instance_class     = "db.t3.medium"
}
