import importlib
import json
import os
import sys
from typing import Any, TypeVar, Union

import boto3
import httpx
from packaging import version
from requests_aws4auth import AWS4Auth

os.environ["OPENAI_API_KEY"] = "sk-XXX"

openai_orig = importlib.import_module("openai")
parsed_version = version.parse(openai_orig.__version__)
major = parsed_version.major
assert (
    parsed_version.major == 0 and parsed_version >= version.parse("0.28.1")
) or parsed_version >= version.parse("1.1.1")

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


globals().update(vars(openai_orig))
sys.modules["openai"] = sys.modules["openai_wrapi"]

if major == 0:  # TODO
    import requests
    import threading
    import time
    from typing import  Dict, Optional, Tuple

    from openai import (
        error,
        util,
        _make_session,
        MAX_SESSION_LIFETIME_SECS,
        TIMEOUT_SECS,
    )

    _thread_context = threading.local()

    def _request_raw_proxy(
        self,
        method,
        url,
        *,
        params=None,
        supplied_headers: Optional[Dict[str, str]] = None,
        files=None,
        stream: bool = False,
        request_id: Optional[str] = None,
        request_timeout: Optional[Union[float, Tuple[float, float]]] = None,
    ) -> requests.Response:
        abs_url, headers, data = self._prepare_request_raw(
            url, supplied_headers, method, params, files, request_id
        )

        if not hasattr(_thread_context, "session"):
            _thread_context.session = _make_session()
            _thread_context.session_create_time = time.time()
        elif (
            time.time() - getattr(_thread_context, "session_create_time", 0)
            >= MAX_SESSION_LIFETIME_SECS
        ):
            _thread_context.session.close()
            _thread_context.session = _make_session()
            _thread_context.session_create_time = time.time()
        try:
            result = _thread_context.session.request(
                method,
                abs_url,
                headers=headers,
                data=data,
                files=files,
                stream=stream,
                timeout=request_timeout if request_timeout else TIMEOUT_SECS,
                proxies=_thread_context.session.proxies,
            )
        except requests.exceptions.Timeout as e:
            raise error.Timeout("Request timed out: {}".format(e)) from e
        except requests.exceptions.RequestException as e:
            raise error.APIConnectionError(
                "Error communicating with OpenAI: {}".format(e)
            ) from e
        util.log_debug(
            "OpenAI API response",
            path=abs_url,
            response_code=result.status_code,
            processing_ms=result.headers.get("OpenAI-Processing-Ms"),
            request_id=result.headers.get("X-Request-Id"),
        )
        # Don't read the whole stream for debug logging unless necessary.
        if openai_orig.log == "debug":
            util.log_debug(
                "API response body", body=result.content, headers=result.headers
            )
        return result

    # Monkey patch
    openai_orig.api_requestor.APIRequestor.request_raw = _request_raw_proxy

else:
    from openai._client import OpenAI
    from openai._base_client import BaseClient
    from openai._streaming import Stream, AsyncStream

    _HttpxClientT = TypeVar(
        "_HttpxClientT", bound=Union[httpx.Client, httpx.AsyncClient]
    )
    _DefaultStreamT = TypeVar(
        "_DefaultStreamT", bound=Union[Stream[Any], AsyncStream[Any]]
    )

    session = boto3.Session()
    credentials = session.get_credentials()
    aws_auth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        session.region_name,
        "lambda",
        session_token=credentials.token,
    )
    url = "https://hmvexdwxxex245kwvsbkl6lggy0grgcv.lambda-url.eu-central-1.on.aws/"

    class BaseClientProxy(BaseClient[_HttpxClientT, _DefaultStreamT]):
        custom_auth = aws_auth

    class OpenAIProxy(BaseClientProxy[httpx.Client, Stream[Any]], OpenAI):
        pass

    client = OpenAIProxy(base_url=url)
    client.base_url = url

    for attr in dir(client):
        if not attr.startswith("__"):
            globals()[attr] = getattr(client, attr)


lambda_client = boto3.client("lambda")


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
