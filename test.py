# TODO
# streaming in python not working
# headers not in context! check other headers - options
# project, user
# handle errors
# get v0 working
# test streaming https://github.com/openai/openai-cookbook/blob/main/examples/How_to_stream_completions.ipynb
# test with langchain
# tidy and refactor

# Make sure you do this before importing any packages that use openai under the hood
import openai_wrapi as openai


# User must have IAM permissions to invoke openai-admin-dev
openai.set_limit(staging="dev", project="hello", limit=10)
# openai.flush_cache()

# Limits must have been set for the project
openai.set_project("hello")
# openai.set_caching(False)

response = openai.chat.completions.create(
    model='gpt-3.5-turbo',
    messages=[
        {'role': 'user', 'content': "Tell me a story in 100 words."}
    ],
    temperature=0,
    stream=True  # this time, we set stream=True
)

for chunk in response:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end='')
print()

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
