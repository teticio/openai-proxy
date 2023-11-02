from base64 import b64encode

from openai.api_requestor import APIRequestor


def lambda_handler(event, context):
    requestor = APIRequestor()
    result = requestor.request_raw(
        event.get("method").lower(),
        event.get("url"),
        params=event.get("params"),
        supplied_headers=event.get("headers"),
        files=event.get("files"),
        stream=event.get("stream"),
        request_id=event.get("request_id"),
        request_timeout=event.get("request_timeout"),
    )
    return {
        "headers": dict(result.headers),
        "content": b64encode(result.content),
        "status_code": result.status_code,
    }


if __name__ == "__main__":
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
