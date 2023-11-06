import boto3
import json
from base64 import b64decode
from types import SimpleNamespace
from typing import Iterator, Optional, Tuple, Union

import openai as openai_orig
from openai import *
from openai.openai_response import OpenAIResponse

cache = {}
project = "N/A"
staging = "dev"


def set_project(project_name: str):
    global project
    project = project_name


def set_staging(staging_name: str):
    global staging
    staging = staging_name


def clear_cache():
    global cache
    cache = {}


def get_user():
    session = boto3.Session()
    profile = None
    profiles = session._session.full_config["profiles"]
    if session.profile_name in profiles:
        profile = session._session.full_config["profiles"][session.profile_name]
        if "source_profile" in profile:
            profile = profile["source_profile"]
    user = (
        boto3.Session(profile_name=profile).client("sts").get_caller_identity()["Arn"]
    )
    return user


user = get_user()
lambda_client = boto3.client("lambda")


def request_proxy(
    self,
    method,
    url,
    params=None,
    headers=None,
    files=None,
    stream: bool = False,
    request_id: Optional[str] = None,
    request_timeout: Optional[Union[float, Tuple[float, float]]] = None,
) -> Tuple[Union[OpenAIResponse, Iterator[OpenAIResponse]], bool, str]:
    key = json.dumps({"url": url, "params": params})
    if key in cache:
        return cache[key], False, self.api_key
    payload = {
        "method": method,
        "url": url,
        "params": params,
        "headers": headers,
        "files": files,
        "stream": stream,
        "request_id": request_id,
        "request_timeout": request_timeout,
        "user": user,
        "project": project,
    }
    result = SimpleNamespace(
        **json.loads(
            lambda_client.invoke(
                FunctionName=f"openai-proxy-{staging}",
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )["Payload"].read()
        )
    )
    if hasattr(result, "errorMessage"):
        exception = getattr(error, result.errorType, Exception)
        raise exception(result.errorMessage + "\n" + "\n".join(result.stackTrace))
    result.content = b64decode(result.content)
    resp, got_stream = self._interpret_response(result, stream)
    if not got_stream:
        cache[key] = resp
    return resp, got_stream, self.api_key


openai_orig.api_requestor.APIRequestor.request = request_proxy
__all__ = [name for name in dir(openai_orig) if not name.startswith("_")]
globals().update({name: getattr(openai_orig, name) for name in __all__})


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
        raise Exception(result["errorMessage"] + "\n" + "\n".join(result["stackTrace"]))
