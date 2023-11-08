import hashlib
import json
import os
from base64 import b64decode, b64encode
from datetime import datetime
from decimal import Decimal

import boto3
import httpx
from httpx import Limits, Request, Timeout
from pymemcache.client.base import Client

TTL = 60 * 60 * 24  # 1 day
cache_endpoint = os.getenv("ELASTICACHE", "")
cache_port = 11211
client = Client((cache_endpoint, cache_port)) if cache_endpoint != "" else None

prices = {
    "gpt-3.5-turbo": (0.0015, 0.002),
    "gpt-3.5-turbo-16k": (0.003, 0.004),
    "gpt-3.5-turbo-instruct": (0.0015, 0.002),
    "gpt-4": (0.03, 0.06),
    "gpt-4-32k": (0.06, 0.12),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price = prices.get(model, (0, 0))
    cost = price[0] * input_tokens / 1000 + price[1] * output_tokens / 1000
    return cost


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("openai-usage")


def get_usage_and_limit(composite_key):
    current_month = datetime.now().strftime("%m%y")
    usage = limit = None
    response = table.get_item(
        Key={
            "composite_key": composite_key,
        }
    )
    if "Item" in response:
        limit = response["Item"].get("limit")
        usage = response["Item"].get(current_month, Decimal(0))
    return usage, limit


def update_usage(user, project, model, staging, cost):
    current_month = datetime.now().strftime("%m%y")
    composite_key = f"{user}#{project}#{model}#{staging}"
    table.update_item(
        Key={
            "composite_key": composite_key,
        },
        UpdateExpression="SET #month = if_not_exists(#month, :zero) + :cost, "
        "#user = :user, #project = :project, #model = :model, #staging = :staging",
        ExpressionAttributeValues={
            ":zero": Decimal(0),
            ":cost": Decimal(str(cost)),
            ":user": user,
            ":project": project,
            ":model": model,
            ":staging": staging,
        },
        ExpressionAttributeNames={
            "#month": current_month,
            "#user": "user",
            "#project": "project",
            "#model": "model",
            "#staging": "staging",
        },
    )


def lambda_handler(event, context):
    user = event["user"]
    project = event.get("project", "N/A")
    staging = os.environ["STAGING"]
    content = b64decode(event["content"]).decode()
    headers = event["headers"]
    headers["authorization"] = f'Bearer {os.getenv("OPENAI_API_KEY")}'
    headers["openai-organization"] = f'{os.getenv("OPENAI_ORGANIZATION")}'
    model = (
        headers["openai-model"]
        if "openai-model" in headers
        else json.loads(content)["model"]
    )
    if model not in prices:
        model = model[: model.rfind("-")]

    if client is not None and "nocache" not in event:
        hash_object = hashlib.sha256()
        hash_object.update(event["content"].encode())
        key = hash_object.hexdigest()
        result = client.get(key)
        if result is not None:
            return json.loads(result)

    project_usage, project_limit = get_usage_and_limit(
        composite_key=f"*#{project}#*#{staging}"
    )
    if project_limit is not None and project_usage >= project_limit:
        raise Exception(f"Project {project} usage limit exceeded")
    model_usage, model_limit = get_usage_and_limit(
        composite_key=f"*#{project}#{model}#{staging}"
    )
    if model_limit is not None and model_usage >= model_limit:
        raise Exception(f"Project {project} usage limit exceeded for model {model}")
    if project_limit is None and model_limit is None:
        raise Exception(f"Project {project} must have a usage limit")
    user_usage, user_limit = get_usage_and_limit(
        composite_key=f"{user}#{project}#{model}#{staging}"
    )
    if user_limit is not None and user_usage >= user_limit:
        raise Exception(
            f"User {user} usage limit exceeded for project {project} and model {model}"
        )

    _client = httpx.Client(
        timeout=Timeout(connect=5.0, read=600.0, write=600.0, pool=600.0),
        limits=Limits(
            max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0
        ),
    )
    result = _client.send(
        request=Request(
            method=event.get("method"),
            url=event.get("url"),
            content=content,
            headers=headers,
        ),
    )

    resp = json.loads(result.content)
    if "error" not in resp:
        cost = calculate_cost(
            model=resp["model"],
            input_tokens=resp["usage"]["prompt_tokens"],
            output_tokens=resp["usage"]["completion_tokens"],
        )
        update_usage(
            user=user,
            project=project,
            model=model,
            staging=staging,
            cost=cost,
        )
        update_usage(
            user="*",
            project=project,
            model=model,
            staging=staging,
            cost=cost,
        )
        update_usage(
            user="*",
            project=project,
            model="*",
            staging=staging,
            cost=cost,
        )

    result.raise_for_status()
    result = {
        "content": b64encode(result.content).decode(),
        "headers": dict(result.headers),
        "reason_phrase": result.reason_phrase,
        "status_code": result.status_code,
    }

    if client is not None and "nocache" not in event:
        client.set(key, json.dumps(result), expire=TTL)

    return result


if __name__ == "__main__":  # for testing
    os.environ["STAGING"] = "dev"
    print(
        b64decode(
            lambda_handler(
                {
                    "method": "POST",
                    "url": "https://api.openai.com/v1/chat/completions",
                    "content": b64encode(
                        json.dumps(
                            {
                                "messages": [
                                    {"role": "user", "content": "Hello world"}
                                ],
                            }
                        ).encode()
                    ),
                    "headers": {
                        "content-type": "application/json",
                        "openai-model": "gpt-3.5-turbo-0613",
                    },
                    "project": "hello",
                    "user": "fulano",
                },
                None,
            )["content"]
        ).decode()
    )
