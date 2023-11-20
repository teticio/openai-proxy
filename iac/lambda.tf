resource "aws_security_group" "openai_lambda" {
  name   = "openai-lambda"
  vpc_id = module.vpc.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_iam_policy" "lambda_dynamodb" {
  name        = "openai-lambda-dynamodb"
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

resource "aws_iam_role" "lambda_exec" {
  name = "openai-lambda-exec"

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

resource "aws_iam_role_policy_attachment" "lambda_dynamodb" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_dynamodb.arn
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_access" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_lambda_function" "openai_proxy" {
  for_each      = var.stages
  function_name = "openai-proxy-${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  image_uri     = module.openai_proxy.image_uri
  package_type  = "Image"
  timeout       = 600
  publish       = true

  environment {
    variables = {
      ELASTICACHE    = var.use_elasticache ? aws_elasticache_cluster.memcached[0].cluster_address : ""
      OPENAI_API_KEY = each.value.openai_api_key
      OPENAI_ORG_ID  = each.value.openai_org_id
    }
  }

  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.openai_lambda.id]
  }
}

resource "aws_lambda_function" "openai_admin" {
  for_each      = var.stages
  function_name = "openai-admin-${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  image_uri     = module.openai_admin.image_uri
  package_type  = "Image"
  publish       = true

  environment {
    variables = {
      ELASTICACHE = var.use_elasticache ? aws_elasticache_cluster.memcached[0].cluster_address : ""
    }
  }

  vpc_config {
    subnet_ids         = module.vpc.private_subnets
    security_group_ids = [aws_security_group.openai_lambda.id]
  }
}

module "openai_proxy" {
  source          = "terraform-aws-modules/lambda/aws//modules/docker-build"
  create_ecr_repo = true
  ecr_repo        = "openai-proxy"
  source_path     = "${path.module}/openai_proxy"
  platform        = "linux/amd64"

  image_tag = sha1(join("", [
    filesha1("${path.module}/openai_proxy/package.json"),
    filesha1("${path.module}/openai_proxy/app.js"),
    filesha1("${path.module}/openai_proxy/prices.js"),
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

resource "aws_lambda_function_url" "openai_proxy" {
  for_each           = var.stages
  function_name      = aws_lambda_function.openai_proxy[each.key].function_name
  authorization_type = "AWS_IAM"
  invoke_mode        = "RESPONSE_STREAM"
}
