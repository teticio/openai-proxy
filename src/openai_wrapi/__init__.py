import importlib
import sys

from packaging import version

from .utils import flush_cache, set_limit  # noqa: F401

openai_orig = importlib.import_module("openai")
parsed_version = version.parse(openai_orig.__version__)
major = parsed_version.major
assert (
    parsed_version.major == 0 and parsed_version >= version.parse("0.28.1")
) or parsed_version >= version.parse("1.2.3")


if major == 0:
    from .proxy0 import (
        _request_raw_proxy,
        set_caching,
        set_project,
        set_staging,
    )  # noqa: F401

    # Monkey patch
    openai_orig.api_requestor.APIRequestor.request_raw = _request_raw_proxy
    globals().update(vars(openai_orig))
    sys.modules["openai"] = sys.modules["openai_wrapi"]

else:
    from .proxy1 import OpenAIProxy

    globals().update(vars(openai_orig))
    sys.modules["openai"] = sys.modules["openai_wrapi"]
    client = OpenAIProxy()
    for attr in dir(client):
        if not attr.startswith("__"):
            globals()[attr] = getattr(client, attr)
    OpenAI = OpenAIProxy

sys.modules["openai"] = sys.modules["openai_wrapi"]
