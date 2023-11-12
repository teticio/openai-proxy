output "openai_proxy_dev_url" {
  value = aws_lambda_function_url.openai_proxy_dev.function_url
}

output "openai_proxy_prod_url" {
  value = aws_lambda_function_url.openai_proxy_prod.function_url
}
