import os
import sys

import anthropic

# # Never hard-code keys here: run as  ANTHROPIC_API_KEY=sk-ant-... python misc/anthropic_ai_api.py
# if not os.environ.get("ANTHROPIC_API_KEY"):
# 	sys.exit("Set ANTHROPIC_API_KEY to your Anthropic API key (it starts with sk-ant-).")
# ANTHROPIC_API_KEY="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"


ANTHROPIC_API_KEY="sk-..."

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

response = client.beta.messages.create(
	model="claude-opus-5-5",
	max_tokens=16000,
	system="You are a coding assistant that talks like a pirate.",
	messages=[{"role": "user", "content": "How do I check if a Python object is an instance of a class?"}],
	# If a safety classifier declines, Anthropic re-runs the request on its recommended fallback model.
	betas=["server-side-fallback-2026-07-01"],
	fallbacks="default",
)

if response.stop_reason == "refusal":
	sys.exit(f"Refused: {response.stop_details.explanation if response.stop_details else 'no details'}")

print("".join(block.text for block in response.content if block.type == "text"))
