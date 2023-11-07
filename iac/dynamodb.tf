data "aws_route_table" "openai" {
  count     = length(module.vpc.private_subnets)
  subnet_id = module.vpc.private_subnets[count.index]
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for r in data.aws_route_table.openai : r.route_table_id]
}

resource "aws_dynamodb_table" "openai_usage" {
  name         = "openai-usage"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "composite_key"

  attribute {
    name = "composite_key"
    type = "S"
  }

  attribute {
    name = "user"
    type = "S"
  }

  attribute {
    name = "project"
    type = "S"
  }

  attribute {
    name = "model"
    type = "S"
  }

  attribute {
    name = "staging"
    type = "S"
  }

  global_secondary_index {
    name            = "user-index"
    hash_key        = "user"
    write_capacity  = 1
    read_capacity   = 1
    projection_type = "KEYS_ONLY"
  }

  global_secondary_index {
    name            = "project-index"
    hash_key        = "project"
    write_capacity  = 1
    read_capacity   = 1
    projection_type = "KEYS_ONLY"
  }

  global_secondary_index {
    name            = "model-index"
    hash_key        = "model"
    write_capacity  = 1
    read_capacity   = 1
    projection_type = "KEYS_ONLY"
  }

  global_secondary_index {
    name            = "staging-index"
    hash_key        = "staging"
    write_capacity  = 1
    read_capacity   = 1
    projection_type = "KEYS_ONLY"
  }
}
