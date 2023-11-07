import importlib
import json
import logging
import os
import sys
from base64 import b64decode, b64encode
from types import SimpleNamespace
from typing import Any, Type, TypeVar

import boto3
import httpx
from openai._exceptions import APIConnectionError, APITimeoutError
from openai._models import FinalRequestOptions
from openai._streaming import Stream
from openai._types import ResponseT
from packaging import version

openai_orig = importlib.import_module("openai")
assert version.parse(openai_orig.__version__) >= version.parse("1.1.1")

os.environ["OPENAI_API_KEY"] = "XXX"

project = "N/A"
staging = "dev"
caching = True


def set_project(project_name: str):
    global project
    project = project_name


def set_staging(staging_name: str):
    global staging
    staging = staging_name


def set_caching(caching_value: bool):
    global caching
    caching = caching_value


def get_user():
    session = boto3.Session()
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


log: logging.Logger = logging.getLogger(openai_orig.__name__)
_StreamT = TypeVar("_StreamT", bound=Stream[Any])


def _request_proxy(
    self,
    *,
    cast_to: Type[ResponseT],
    options: FinalRequestOptions,
    remaining_retries: int | None,
    stream: bool,
    stream_cls: type[_StreamT] | None,
) -> ResponseT | _StreamT:
    self._prepare_options(options)

    retries = self._remaining_retries(remaining_retries, options)
    request = self._build_request(options)
    self._prepare_request(request)

    try:
        response = _send(request, auth=self.custom_auth, stream=stream)
        log.debug(
            'HTTP Request: %s %s "%i %s"',
            request.method,
            request.url,
            response.status_code,
            response.reason_phrase,
        )
        # response.raise_for_status()
    except httpx.HTTPStatusError as err:  # thrown on 4xx and 5xx status code
        if retries > 0 and self._should_retry(err.response):
            return self._retry_request(
                options,
                cast_to,
                retries,
                err.response.headers,
                stream=stream,
                stream_cls=stream_cls,
            )

        # If the response is streamed then we need to explicitly read the response
        # to completion before attempting to access the response text.
        err.response.read()
        raise self._make_status_error_from_response(err.response) from None
    except httpx.TimeoutException as err:
        if retries > 0:
            return self._retry_request(
                options,
                cast_to,
                retries,
                stream=stream,
                stream_cls=stream_cls,
            )
        raise APITimeoutError(request=request) from err
    except Exception as err:
        if retries > 0:
            return self._retry_request(
                options,
                cast_to,
                retries,
                stream=stream,
                stream_cls=stream_cls,
            )
        raise APIConnectionError(request=request) from err

    return self._process_response(
        cast_to=cast_to,
        options=options,
        response=response,
        stream=stream,
        stream_cls=stream_cls,
    )


user = get_user()
lambda_client = boto3.client("lambda")


def _send(request, auth, stream):
    payload = {
        "method": request.method,
        "url": str(request.url),
        "content": b64encode(request.content).decode(),
        "headers": dict(request.headers),
        "project": project,
        "user": user,
    }
    if not caching:
        payload["nocache"] = True

    response = SimpleNamespace(
        **json.loads(
            lambda_client.invoke(
                FunctionName=f"openai-proxy-{staging}",
                InvocationType="RequestResponse",
                Payload=json.dumps(payload),
            )["Payload"].read()
        )
    )

    if hasattr(response, "errorMessage"):
        if hasattr(response, "errorType"):
            exception = getattr(openai_orig._exceptions, response.errorType, Exception)
        else:
            raise Exception(response.errorMessage)
        raise exception(response.errorMessage + "".join(response.stackTrace))

    response.content = b64decode(response.content)
    response.request = request
    response.json = lambda: json.loads(response.content)
    return response


# monkey patch
openai_orig._base_client.SyncAPIClient._request = _request_proxy
globals().update(vars(openai_orig))
sys.modules['openai'] = sys.modules['openai_proxy']

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


def flush_cache():
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
