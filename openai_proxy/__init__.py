import boto3
import json
import os
from base64 import b64decode
from types import SimpleNamespace
from typing import Iterator, Optional, Tuple, Union

import openai as openai_orig
from openai import *
from openai.openai_response import OpenAIResponse

cache = {}
project = "N/A"
lambda_client = boto3.client("lambda")
sts_client = boto3.Session(
    profile_name=os.environ.get("ROOT_AWS_PROFILE", "default")
).client("sts")


def set_project(project_name: str):
    global project
    project = project_name


def clear_cache():
    global cache
    cache = {}


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
    user = sts_client.get_caller_identity()["Arn"]
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
                FunctionName="openai-proxy",
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )["Payload"].read()
        )
    )
    result.content = b64decode(result.content)
    resp, got_stream = self._interpret_response(result, stream)
    if not got_stream:
        cache[key] = resp
    return resp, got_stream, self.api_key


openai_orig.api_requestor.APIRequestor.request = request_proxy
__all__ = [name for name in dir(openai_orig) if not name.startswith("_")]
globals().update({name: getattr(openai_orig, name) for name in __all__})
