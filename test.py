# TODO
# headers not in context! check other headers - options
# handle errors
# get v0 working
# test streaming https://github.com/openai/openai-cookbook/blob/main/examples/How_to_stream_completions.ipynb
# test with langchain
# tidy and refactor

# Make sure you do this before importing any packages that use openai under the hood
import openai_wrapi as openai


# User must have IAM permissions to invoke openai-admin-dev
openai.set_limit(staging="dev", project="hello", limit=10)
openai.flush_cache()

# Limits must have been set for the project
openai.set_project("hello")
# openai.set_caching(False)


for _ in range(2):  # second call returns cached result
    # User must have IAM permissions to invoke openai-proxy-dev
    try:  # openai v1
        completion = openai.chat.completions.create(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
        )
    except AttributeError:  # openai v0
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
        )
    print(completion)
