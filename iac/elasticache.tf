resource "aws_security_group" "openai_elasticache" {
  name   = "openai-elasticache"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 11211
    to_port         = 11211
    protocol        = "tcp"
    security_groups = [aws_security_group.openai_lambda.id]
  }
}

resource "aws_elasticache_subnet_group" "private" {
  name       = "openai-memcached"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_cluster" "memcached" {
  count                = var.use_elasticache ? 1 : 0
  cluster_id           = "openai-memcached"
  engine               = "memcached"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.memcached1.6"
  port                 = 11211
  security_group_ids   = [aws_security_group.openai_elasticache.id]
  subnet_group_name    = aws_elasticache_subnet_group.private.name
}
