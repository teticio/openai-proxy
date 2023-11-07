# OpenAI Proxy

A drop-in wrapper to the `openai` package that tracks cost per user, project, model and staging account. It is built using serverless AWS services.

## Usage

To deploy set the variables listed in `variables.tf` in a `terraform.tfvars` file and run:

```bash
cd iac
terraform init
terraform apply -auto-approve
```

This will create two Lambda functions (one for dev and one for prod) as well as a DynamoDB table to store the usage data. Then, if you `import openai_proxy as openai`, the API calls to OpenAI will be made via the appropriate Lambda function. This has several benefits:
- The OpenAI API keys are hidden in the Lambda function and IAM permissions can be used to control who has access to what.
- Fine-grained usage data is tracked in the DynamoDB table.
- Limits can be set at project, model and user level for each staging account.
- Responses from OpenAI are cached by default.

There are some extra functions provided in the `openai_proxy` package to allow you to `set_project`, `set_staging`, `set_caching` and `flush_cache``. For convenience, a `set_limits` function is provided for users with IAM permissions to run the `openai-admin-{staging}` Lambda function.

## TODO

- Make package installable.
- Dashboard to view usage.
- Rate limits.
- Handle streaming / async requests.
