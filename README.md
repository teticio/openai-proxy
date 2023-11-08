# OpenAI Proxy [`openai-wrapi`]

A drop-in wrapper to the `openai` package that tracks costs per user, project, model and staging account.

## Problem statement

OpenAI does not currently provide any way to monitor or limit API usage costs by user*, project or model. In fact, there is no concept of "project", only users (which correspond to email addresses), organizations (which correspond to OpenAI accounts and must be individually funded) and API keys (which can be used interchangeably across any organizations to which a user belongs).

This leads to a proliferation of API keys and users opening up a wider attack surface from a security point of view. Furthermore, users cannot be forced to use MFA and may continue to use the API and create API keys, even if their email no longer exists.

Lastly, it is easy to make redundant calls to the API incurring unnecessary costs, especially when developing in an interactive environment such as a Jupyter notebook.

\* The latest version of the OpenAI usage dashboard shows number of calls per user, but not cost.

## Solution

This repo provides a wrapper which checks usage limits before passing on the request to the OpenAI API and records the usage costs per user, project, model and staging account. It leverages the IAM permission framework of AWS to control access to the OpenAI API, without exposing the unique API keys per staging account. Responses from the OpenAI API are cached by default. Infrastructure As Code (IAC) is given to deploy the solution using a serverless architecture in AWS at a minimal extra cost and latency.

## Deploy

Ideally, you should have one OpenAI account per staging account (dev, prod). Create a `terraform.tfvars` file in the `iac` directory with the following variables:

```terraform
profile                  = "default"   # AWS profile to use
region                   = "eu-west-2" # AWS region to deploy to
openai_api_key_dev       = "sk-XXX"    # OpenAI API key for dev account
openai_organization_dev  = "org-XXX"   # OpenAI organization ID for dev account
openai_api_key_prod      = "sk-YYY"    # OpenAI API key for prod account
openai_organization_prod = "org-YYY"   # OpenAI organization ID for prod account
num_azs                  = 3           # Number of availability zones to deploy to (limited by available Elastic IP addresses)
use_elasticache          = true        # Whether to use ElastiCache Memcache
```

To deploy run:

```bash
cd iac
terraform init
terraform apply -auto-approve
```

This will create
- A Lambda function to proxy calls to the OpenAI API per staging account (dev, prod).
- A Lambda function to set usage limits and flush the cache per staging account (dev, prod).
- A DynamoDB table to store usage and limit data per staging account (dev, prod).
- An optional ElastiCache Memcache cluster to cache OpenAI API responses.

# Install

From PyPI

```bash
pip install openai-wrapi
```

From source

```bash
git clone
cd openai-proxy
pip install .
```

## Usage

In order to use the proxy in your Python code, provided you have the appropriate IAM permissions, you can run:

```python
import openai_proxy as openai
```

You no longer need set the OpenAI API key or organization ID as these are securely stored in the corresponding Lambda functions. If you plan to use packages such as `langchain` which use the `openai` package internally, you need only ensure you have previously imported `openai_proxy`.

By default, the project associated with any API calls will be `N/A`. In order to set the project name:

```python
openai.set_project("my-project")
```

If you want to disable caching (enabled by default):
    
```python
openai.set_caching(False)
```

## Admin

Again, supposing you have the IAM permissions to be able to invoke the `openai-admin-{staging}` Lambda function, you can

- set the usage limits per user, project and model:

```python
openai.set_limits(
    limit=10,              # 10 USD
    staging="dev",         # Dev account
    project="my-project",  # Project name
    user="me",             # Optional
    model="gpt-4",         # Optional
)
```

- flush the cache:

```python
openai.flush_cache()
```

Note that this wrapper currently works for major versions 0 and 1 of the `openai` package.

## TODO

- Pass in timeout
- Dashboard to view usage.
- Rate limits.
- Handle streaming / async requests.
