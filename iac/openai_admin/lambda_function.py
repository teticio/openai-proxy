import os
from decimal import Decimal

import boto3


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
    set_limit(
        user=event.get("user", "*"),
        project=event.get("project"),
        model=event.get("model", "*"),
        staging=os.environ["STAGING"],
        limit=event.get("limit"),
    )
    return {
        "status_code": 200,
    }


if __name__ == "__main__":  # for testing
    os.environ["STAGING"] = "dev"
    print(
        lambda_handler(
            {
                "project": "hello",
                "limit": 10,
            },
            None,
        )
    )
