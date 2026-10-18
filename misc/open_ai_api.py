import os
import sys

from openai import OpenAI

# Gemini through its OpenAI-compatible endpoint. Never hard-code keys here:
#   GEMINI_API_KEY=AQ.... python misc/apen_ai_api.py
# api_key = os.environ.get("GEMINI_API_KEY")
api_key = "AQ.Ab8RN6IzI4C6Lna91793nAKIXyBanKIgBvLvRl_2G3yXkOfFeQ"  # Replace with your actual API key
if not api_key:
	sys.exit("Set GEMINI_API_KEY to your Gemini API key from Google AI Studio.")

client = OpenAI(api_key=api_key, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

response = client.chat.completions.create(
	model="gemini-3.8-flash",
	messages=[
		{"role": "system", "content": "You are a coding assistant that talks like a pirate."},
		{"role": "user", "content": "How do I check if a Python object is an instance of a class?"},
	],
)

print(response.choices[0].message.content)
