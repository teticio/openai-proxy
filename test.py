# TODO
# get v0 working
# test with langchain
# tidy and refactor
# refresh auth

# Make sure you do this before importing any packages that use openai under the hood.
import openai_wrapi as openai
from time import sleep

# User must have IAM permissions to invoke openai-admin-dev.
openai.set_limit(staging="dev", project="hello", limit=10)
openai.flush_cache(staging="dev")

# Limits must have been set for the project.
openai.set_project("hello")
# openai.set_caching(False).

for _ in range(
    2
):  # Second call returns cached result (provided there is a short delay between calls).
    # User must have IAM permissions to invoke openai-proxy-dev
    # and have set OPENAI_API_KEY to be sk-XXX, where XXX corresponds to the URL
    # https://XXX.lambda-url.region.on.aws/ of your Lambda function.
    try:  # openai v1
        completion = openai.chat.completions.create(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
        )
    except AttributeError:  # openai v0
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
        )
    print(completion)
    sleep(1)

# Test streaming.
try:  # openai v1
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Tell me a story in 10 words."}],
        temperature=0,
        stream=True,
    )
except AttributeError:  # openai v0
    completion = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": "Tell me a story in 10 words."}],
        temperature=0,
        stream=True,
    )

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
print()
