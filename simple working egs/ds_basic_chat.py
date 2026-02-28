import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get('DS_API_KEY'),
    base_url="https://api.deepseek.com")

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Tell me a fun joke pls"},
    ],
    extra_body={ "thinking": { "type": "enabled" } },
    stream=False
)
print("reasoning content:")
print(response.choices[0].message.reasoning_content)
print("content:")
print(response.choices[0].message.content)