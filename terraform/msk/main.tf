# ----------------------------------------------------
# MSK Module (Amazon Managed Streaming for Apache Kafka)
# ----------------------------------------------------

resource "aws_security_group" "msk" {
  name        = "${var.environment}-msk-sg"
  description = "Allow inbound Kafka traffic from EKS node group"
  vpc_id      = var.vpc_id

  ingress {
    description     = "Kafka PLAINTEXT port 9092"
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [var.allowed_security_group_id]
  }

  ingress {
    description     = "Kafka TLS port 9094"
    from_port       = 9094
    to_port         = 9094
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
    Name        = "${var.environment}-msk-sg"
    Environment = var.environment
  }
}

resource "aws_msk_cluster" "kafka" {
  cluster_name           = "${var.environment}-kafka-broker"
  kafka_version          = "3.6.0"
  number_of_broker_nodes = 2

  broker_node_group_info {
    instance_type = "kafka.t3.small"
    client_subnets = var.private_subnet_ids
    security_groups = [aws_security_group.msk.id]
    
    storage_info {
      ebs_storage_info {
        volume_size = 10
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS_PLAINTEXT" # For development, permit PLAINTEXT + TLS
      in_cluster    = true
    }
  }

  tags = {
    Name        = "${var.environment}-kafka-cluster"
    Environment = var.environment
  }
}
