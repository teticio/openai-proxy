from typing import Any, TypeVar, Union

import httpx
from httpx import URL
from openai._base_client import BaseClient
from openai._client import OpenAI
from openai._streaming import AsyncStream, Stream

from .utils import get_aws_auth, get_base_url, get_user

_HttpxClientT = TypeVar("_HttpxClientT", bound=Union[httpx.Client, httpx.AsyncClient])
_DefaultStreamT = TypeVar("_DefaultStreamT", bound=Union[Stream[Any], AsyncStream[Any]])


class BaseClientProxy(BaseClient[_HttpxClientT, _DefaultStreamT]):
    custom_auth = get_aws_auth()


class OpenAIProxy(BaseClientProxy[httpx.Client, Stream[Any]], OpenAI):
    def __init__(
        self,
        project: str = "N/A",
        staging: str = "dev",
        caching: str = "1",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._custom_headers["openai-proxy-project"] = project
        self._custom_headers["openai-proxy-staging"] = staging
        self._custom_headers["openai-proxy-user"] = get_user()
        self._custom_headers["openai-proxy-caching"] = str(int(caching))
        self._base_url = URL(get_base_url(self.api_key.split("-")[1]))
