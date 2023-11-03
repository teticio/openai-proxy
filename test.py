# TODO
# error handling
# control usage
# add / remove users
# dashboard
# elasticache

import openai_proxy as openai

openai.set_project("hello")
completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
)
print(completion)

completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
)
print(completion)
