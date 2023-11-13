variable "region" {
  type = string
}

variable "profile" {
  type = string
}

variable "stages" {
  type = map(object({ openai_api_key = string, openai_org_id = string }))
}

variable "num_azs" {
  type    = number
  default = 3
}

variable "use_elasticache" {
  type    = bool
  default = false
}
