import os
from typing import Any, TypeVar, Union

import httpx
from httpx import URL
from openai._base_client import BaseClient
from openai._client import AsyncOpenAI, OpenAI
from openai._streaming import AsyncStream, Stream

from .utils import get_aws_auth, get_base_url, get_user

_HttpxClientT = TypeVar("_HttpxClientT", bound=Union[httpx.Client, httpx.AsyncClient])
_DefaultStreamT = TypeVar("_DefaultStreamT", bound=Union[Stream[Any], AsyncStream[Any]])


class BaseClientProxy(BaseClient[_HttpxClientT, _DefaultStreamT]):
    custom_auth = get_aws_auth()


class Proxy:
    def __init__(
        self,
        project: str = os.environ.get("OPENAI_DEFAULT_PROJECT", "N/A"),
        staging: str = os.environ.get("OPENAI_DEFAULT_STAGING", "dev"),
        caching: str = os.environ.get("OPENAI_DEFAULT_CACHING", "1"),
    ):
        self.set_project(project)
        self.set_staging(staging)
        self.set_caching(caching)
        self._custom_headers["openai-proxy-user"] = get_user()
        self._base_url = URL(get_base_url(self.api_key.split("-")[1]))

    def set_project(self, project: str):
        self._custom_headers["openai-proxy-project"] = project

    def set_staging(self, staging: str):
        self._custom_headers["openai-proxy-staging"] = staging

    def set_caching(self, caching: bool):
        self._custom_headers["openai-proxy-caching"] = str(int(caching))


class OpenAIProxy(BaseClientProxy[httpx.Client, Stream[Any]], OpenAI, Proxy):
    def __init__(self, **kwargs):
        OpenAI.__init__(self, **kwargs)
        Proxy.__init__(self, **kwargs)

class AsyncOpenAIProxy(BaseClientProxy[httpx.Client, Stream[Any]], AsyncOpenAI, Proxy):
    def __init__(self, **kwargs):
        AsyncOpenAI.__init__(self, **kwargs)
        Proxy.__init__(self, **kwargs)
