import os
from decimal import Decimal

import boto3
from pymemcache.client.base import Client

cache_endpoint = os.getenv("ELASTICACHE", "")
cache_port = 11211
client = Client((cache_endpoint, cache_port)) if cache_endpoint != "" else None


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("openai-usage")


def set_limit(user, project, model, staging, limit):
    composite_key = f"{user}#{project}#{model}#{staging}"
    table.update_item(
        Key={
            "composite_key": composite_key,
        },
        UpdateExpression="SET #limit = :limit, "
        "#user = :user, #project = :project, #model = :model, #staging = :staging",
        ExpressionAttributeValues={
            ":limit": Decimal(str(limit)),
            ":user": user,
            ":project": project,
            ":model": model,
            ":staging": staging,
        },
        ExpressionAttributeNames={
            "#limit": "limit",
            "#user": "user",
            "#project": "project",
            "#model": "model",
            "#staging": "staging",
        },
    )


def lambda_handler(event, context):
    if "flush_cache" in event:
        client.flush_all()
        return {
            "status_code": 200,
        }

    set_limit(
        user=event.get("user", "*"),
        project=event.get("project"),
        model=event.get("model", "*"),
        staging=context.function_name.split("-")[-1],
        limit=event.get("limit"),
    )
    return {
        "status_code": 200,
    }


if __name__ == "__main__":  # for testing
    print(
        lambda_handler(
            {
                "project": "hello",
                "limit": 10,
            },
            {"functionName": "openai-admin-dev"},
        )
    )
