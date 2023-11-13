import json

import boto3
from requests_aws4auth import AWS4Auth

session = boto3.Session()
lambda_client = boto3.client("lambda")


def get_aws_auth():
    aws_auth = AWS4Auth(
        region=session.region_name,
        service="lambda",
        refreshable_credentials=session.get_credentials(),
    )
    return aws_auth


def get_base_url(key: str):
    return f"https://{key}.lambda-url.{session.region_name}.on.aws/"


def get_user():
    profile = session.profile_name
    profiles = session._session.full_config["profiles"]
    if profile in profiles:
        config = session._session.full_config["profiles"][session.profile_name]
        if "source_profile" in config:
            profile = config["source_profile"]
    user = (
        boto3.Session(profile_name=profile).client("sts").get_caller_identity()["Arn"]
    )
    return user


def set_limit(
    limit: float, staging: str, project: str, model: str = "*", user: str = "*"
):
    payload = {
        "project": project,
        "user": user,
        "model": model,
        "limit": limit,
    }
    result = json.loads(
        lambda_client.invoke(
            FunctionName=f"openai-admin-{staging}",
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )["Payload"].read()
    )
    if "errorMessage" in result:
        raise Exception(result["errorMessage"])


def flush_cache(staging: str):
    payload = {
        "flush_cache": True,
    }
    result = json.loads(
        lambda_client.invoke(
            FunctionName=f"openai-admin-{staging}",
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )["Payload"].read()
    )
    if "errorMessage" in result:
        raise Exception(result["errorMessage"])
