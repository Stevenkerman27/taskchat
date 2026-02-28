import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get('SF_API_KEY'),
    base_url="https://api.siliconflow.com/v1/")

response = client.chat.completions.create(
    model="moonshotai/Kimi-K2.5",
    messages=[
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "briefly explain yourself"},
    ],
    stream=False
)

print(response.choices[0].message.content)