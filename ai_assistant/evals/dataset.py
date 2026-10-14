"""The evaluation dataset: kept in the repo, pushed to LangSmith (SPEC §11.2)."""

import hashlib
import json
import os

import frappe

PATH = os.path.join(os.path.dirname(__file__), "dataset.json")


def load() -> list[dict]:
	with open(PATH) as f:
		return json.load(f)


def ensure(client, name: str, examples: list[dict] | None = None) -> str:
	"""Create the LangSmith dataset, or recreate it when the local examples changed."""
	examples = examples if examples is not None else load()
	digest = hashlib.sha256(json.dumps(examples, sort_keys=True).encode()).hexdigest()[:16]
	description = f"ai_assistant evaluation dataset ({digest})"
	if client.has_dataset(dataset_name=name):
		dataset = client.read_dataset(dataset_name=name)
		if dataset.description == description:
			return name
		client.delete_dataset(dataset_name=name)
	dataset = client.create_dataset(dataset_name=name, description=description)
	client.create_examples(
		dataset_id=dataset.id,
		examples=[{"inputs": e["inputs"], "outputs": e["outputs"]} for e in examples],
	)
	frappe.logger("ai_assistant").info(f"Pushed {len(examples)} evaluation examples to {name}")
	return name
