import threading
import time
from typing import Dict, Optional, Tuple, Union
from urllib.parse import urljoin

import requests
from openai import api_key, error, log, util
from openai.api_requestor import (
    MAX_SESSION_LIFETIME_SECS,
    TIMEOUT_SECS,
    _make_session,
)

from .utils import get_aws_auth, get_base_url, get_user

_custom_headers = {
    "openai-proxy-project": "N/A",
    "openai-proxy-staging": "dev",
    "openai-proxy-user": get_user(),
    "openai-proxy-caching": "1",
}
_base_url = get_base_url(api_key.split("-")[1])
_custom_auth = get_aws_auth()


def set_project(project: str):
    _custom_headers["openai-proxy-project"] = project


def set_staging(staging: str):
    _custom_headers["openai-proxy-staging"] = staging


def set_caching(self, caching: bool):
    _custom_headers["openai-proxy-caching"] = str(int(caching))


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
        # Patch request
        result = _thread_context.session.request(
            method,
            urljoin(_base_url, url),
            headers={**headers, **_custom_headers},
            data=data,
            files=files,
            stream=stream,
            timeout=request_timeout if request_timeout else TIMEOUT_SECS,
            proxies=_thread_context.session.proxies,
            auth=_custom_auth,
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
    if log == "debug":
        util.log_debug("API response body", body=result.content, headers=result.headers)
    return result
