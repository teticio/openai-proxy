terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }

    docker = {
      source = "kreuzwerker/docker"
    }
  }
}

provider "aws" {
  profile = var.profile
  region  = var.region
}

data "aws_caller_identity" "this" {}

data "aws_ecr_authorization_token" "token" {}

provider "docker" {
  registry_auth {
    address  = format("%v.dkr.ecr.%v.amazonaws.com", data.aws_caller_identity.this.account_id, var.region)
    username = data.aws_ecr_authorization_token.token.user_name
    password = data.aws_ecr_authorization_token.token.password
  }
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

resource "aws_iam_policy" "lambda_policy" {
  name        = "lambda-dynamodb-policy"
  description = "IAM policy for Lambda to access DynamoDB"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
        ],
        Resource = aws_dynamodb_table.openai_usage.arn
      },
    ]
  })
}

resource "aws_iam_role" "lambda_role" {
  name = "lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

resource "aws_lambda_function" "openai_proxy_dev" {
  function_name = "openai-proxy-dev"
  role          = aws_iam_role.lambda_role.arn
  image_uri     = module.openai_proxy.image_uri
  package_type  = "Image"
  timeout       = 30
  publish       = true

  environment {
    variables = {
      STAGING             = "dev"
      OPENAI_API_KEY      = var.openai_api_key_dev
      OPENAI_ORGANIZATION = var.openai_organization_dev
    }
  }
}

resource "aws_lambda_function" "openai_proxy_prod" {
  function_name = "openai-proxy-prod"
  role          = aws_iam_role.lambda_role.arn
  image_uri     = module.openai_proxy.image_uri
  package_type  = "Image"
  timeout       = 30
  publish       = true

  environment {
    variables = {
      STAGING             = "prod"
      OPENAI_API_KEY      = var.openai_api_key_prod
      OPENAI_ORGANIZATION = var.openai_organization_prod
    }
  }
}

resource "aws_lambda_function" "openai_admin_dev" {
  function_name = "openai-admin-dev"
  role          = aws_iam_role.lambda_role.arn
  image_uri     = module.openai_admin.image_uri
  package_type  = "Image"
  timeout       = 30
  publish       = true

  environment {
    variables = {
      STAGING = "dev"
    }
  }
}

resource "aws_lambda_function" "openai_admin_prod" {
  function_name = "openai-admin-prod"
  role          = aws_iam_role.lambda_role.arn
  image_uri     = module.openai_admin.image_uri
  package_type  = "Image"
  timeout       = 30
  publish       = true

  environment {
    variables = {
      STAGING = "prod"
    }
  }
}

module "openai_proxy" {
  source          = "terraform-aws-modules/lambda/aws//modules/docker-build"
  create_ecr_repo = true
  ecr_repo        = "openai-proxy"
  source_path     = "${path.module}/openai_proxy"
  platform        = "linux/amd64"

  image_tag = sha1(join("", [
    filesha1("${path.module}/openai_proxy/requirements.txt"),
    filesha1("${path.module}/openai_proxy/lambda_function.py"),
    filesha1("${path.module}/openai_proxy/Dockerfile")
  ]))

  ecr_repo_lifecycle_policy = jsonencode({
    "rules" : [
      {
        "rulePriority" : 1,
        "description" : "Keep only the last 1 image",
        "selection" : {
          "tagStatus" : "any",
          "countType" : "imageCountMoreThan",
          "countNumber" : 1
        },
        "action" : {
          "type" : "expire"
        }
      }
    ]
  })
}

module "openai_admin" {
  source          = "terraform-aws-modules/lambda/aws//modules/docker-build"
  create_ecr_repo = true
  ecr_repo        = "openai-admin"
  source_path     = "${path.module}/openai_admin"
  platform        = "linux/amd64"

  image_tag = sha1(join("", [
    filesha1("${path.module}/openai_admin/requirements.txt"),
    filesha1("${path.module}/openai_admin/lambda_function.py"),
    filesha1("${path.module}/openai_admin/Dockerfile")
  ]))

  ecr_repo_lifecycle_policy = jsonencode({
    "rules" : [
      {
        "rulePriority" : 1,
        "description" : "Keep only the last 1 image",
        "selection" : {
          "tagStatus" : "any",
          "countType" : "imageCountMoreThan",
          "countNumber" : 1
        },
        "action" : {
          "type" : "expire"
        }
      }
    ]
  })
}
