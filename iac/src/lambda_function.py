import json
import os
from datetime import datetime
from base64 import b64encode
from decimal import Decimal

import boto3
from openai.api_requestor import APIRequestor

prices = {
    "gpt-3.5-turbo": (0.0015, 0.002),
    "gpt-3.5-turbo-16k": (0.003, 0.004),
    "gpt-3.5-turbo-instruct": (0.0015, 0.002),
    "gpt-4": (0.03, 0.06),
    "gpt-4-32k": (0.06, 0.12),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in prices:
        model = model[: model.rfind("-")]
    price = prices.get(model, (0, 0))
    cost = price[0] * input_tokens / 1000 + price[1] * output_tokens / 1000
    return cost


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("openai-usage")


def update_usage(user, project, model, staging, cost):
    current_month = datetime.now().strftime("%m%y")
    cost = Decimal(str(cost))
    composite_key = f"{user}#{project}#{model}#{staging}"
    response = table.get_item(
        Key={
            "composite_key": composite_key,
        }
    )
    if "Item" in response and current_month in response["Item"]:
        new_cost = response["Item"][current_month] + cost
        table.update_item(
            Key={
                "composite_key": composite_key,
            },
            UpdateExpression="SET #month = :val",
            ExpressionAttributeValues={":val": new_cost},
            ExpressionAttributeNames={"#month": current_month},
        )
    else:
        table.put_item(
            Item={
                "composite_key": composite_key,
                "user": user,
                "project": project,
                "model": model,
                "staging": staging,
                current_month: cost,
            }
        )


def lambda_handler(event, context):
    requestor = APIRequestor()
    result = requestor.request_raw(
        event.get("method").lower(),
        event.get("url"),
        params=event.get("params"),
        supplied_headers=event.get("headers"),
        files=event.get("files"),
        stream=False,  # event.get("stream"),
        request_id=event.get("request_id"),
        request_timeout=event.get("request_timeout"),
    )
    resp = json.loads(result.content)
    cost = calculate_cost(
        model=resp["model"],
        input_tokens=resp["usage"]["prompt_tokens"],
        output_tokens=resp["usage"]["completion_tokens"],
    )
    update_usage(
        user=event.get("user"),
        project=event.get("project"),
        model=resp["model"],
        cost=cost,
        staging=os.environ["STAGING"],
    )
    return {
        "headers": dict(result.headers),
        "content": b64encode(result.content),
        "status_code": result.status_code,
    }


if __name__ == "__main__":  # for testing
    print(
        lambda_handler(
            {
                "method": "post",
                "url": "/chat/completions",
                "params": {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "Hello world"}],
                },
                "headers": None,
                "files": None,
                "stream": False,
                "request_id": None,
                "request_timeout": None,
                "project": "test",
                "user": "fulano",
            },
            None,
        )
    )
