import openai_proxy as openai

# user must have IAM permissions to invoke openai-admin-dev
openai.set_limit(staging="dev", project="hello", limit=10)

# limits must have been set for the project
openai.set_project("hello")
# openai.set_caching(False)

# user must have IAM permissions to invoke openai-proxy-dev
completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
)
print(completion)

# returns cached result
completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo", messages=[{"role": "user", "content": "Hello world"}]
)
print(completion)
