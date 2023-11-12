variable "region" {
  type = string
}

variable "profile" {
  type = string
}

variable "openai_api_key_dev" {
  type = string
}

variable "openai_org_id_dev" {
  type = string
}

variable "openai_api_key_prod" {
  type = string
}

variable "openai_org_id_prod" {
  type = string
}

variable "num_azs" {
  type    = number
  default = 3
}

variable "use_elasticache" {
  type    = bool
  default = false
}
