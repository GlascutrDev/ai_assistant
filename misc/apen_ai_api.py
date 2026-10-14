import os
from openai import OpenAI

OPENAI_API_KEY = "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"

client = OpenAI(
    # This is the default and can be omitted
    api_key=OPENAI_API_KEY,
)

response = client.responses.create(
    model="gpt-5.2",
    instructions="You are a coding assistant that talks like a pirate.",
    input="How do I check if a Python object is an instance of a class?",
)

print(response.output_text)