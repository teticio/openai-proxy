data "aws_availability_zones" "az" {}

module "vpc" {
  source             = "terraform-aws-modules/vpc/aws"
  name               = "openai"
  cidr               = "10.0.0.0/16"
  azs                = [for index in range(var.num_azs) : data.aws_availability_zones.az.names[index]]
  private_subnets    = [for index in range(var.num_azs) : "10.0.${10 + index}.0/24"]
  public_subnets     = [for index in range(var.num_azs) : "10.0.${20 + index}.0/24"]
  enable_nat_gateway = true
}
