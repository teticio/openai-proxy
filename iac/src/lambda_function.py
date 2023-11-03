import json
import logging
from base64 import b64encode

from openai.api_requestor import APIRequestor

logger = logging.getLogger()
logger.setLevel(logging.INFO)

prices = {
    "gpt-3.5-turbo": (0.0015, 0.002),
    "gpt-3.5-turbo-16k": (0.003, 0.004),
    "gpt-3.5-turbo-instruct": (0.0015, 0.002),
    "gpt-4": (0.03, 0.06),
    "gpt-4-32k": (0.06, 0.12),
}


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in prices:
        model = model[: model.rfind("-")]
        if model not in prices:
            logger.error(f"No price found for model {model}")
    price = prices.get(model, (0, 0))
    cost = price[0] * input_tokens / 1000 + price[1] * output_tokens / 1000
    return cost


def lambda_handler(event, context):
    logger.info(f"user: {event.get('user')}")
    logger.info(f"project: {event.get('project')}")
    requestor = APIRequestor()
    result = requestor.request_raw(
        event.get("method").lower(),
        event.get("url"),
        params=event.get("params"),
        supplied_headers=event.get("headers"),
        files=event.get("files"),
        stream=False,  # event.get("stream"),
        request_id=event.get("request_id"),
        request_timeout=event.get("request_timeout"),
    )
    resp = json.loads(result.content)
    cost = calculate_cost(
        model=resp["model"],
        input_tokens=resp["usage"]["prompt_tokens"],
        output_tokens=resp["usage"]["completion_tokens"],
    )
    logger.info(f"model: {resp['model']}")
    logger.info(f"cost: ${cost:.7f}")
    return {
        "headers": dict(result.headers),
        "content": b64encode(result.content),
        "status_code": result.status_code,
    }


if __name__ == "__main__":  # for testing
    print(
        lambda_handler(
            {
                "method": "post",
                "url": "/chat/completions",
                "params": {
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "Hello world"}],
                },
                "headers": None,
                "files": None,
                "stream": False,
                "request_id": None,
                "request_timeout": None,
            },
            None,
        )
    )
