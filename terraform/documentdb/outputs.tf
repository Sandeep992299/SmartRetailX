output "cluster_endpoint" {
  value = aws_docdb_cluster.docdb.endpoint
}

output "security_group_id" {
  value = aws_security_group.docdb.id
}
