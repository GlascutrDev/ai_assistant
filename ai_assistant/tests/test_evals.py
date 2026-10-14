from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.api import settings as settings_api
from ai_assistant.evals import dataset, runner
from ai_assistant.observability import tracing
from ai_assistant.services import settings
from ai_assistant.tests import factories, fake_llm

EXAMPLES = [
	{
		"inputs": {"question": "How many ToDos do I have?"},
		"outputs": {
			"answer": "1",
			"expected_tools": ["count_documents"],
			"expect_write": None,
			"must_refuse": False,
		},
	},
	{
		"inputs": {"question": "Create a ToDo: evaluation write"},
		"outputs": {
			"answer": "Proposed.",
			"expected_tools": ["create_document"],
			"expect_write": {"operation": "create", "doctype": "ToDo"},
			"must_refuse": False,
		},
	},
]


class FakeLangSmith:
	"""Runs the target and evaluators locally, like Client.evaluate, without network."""

	def __init__(self):
		self.datasets = {}

	def __getattr__(self, name):
		return MagicMock()

	def has_dataset(self, dataset_name):
		return dataset_name in self.datasets

	def create_dataset(self, dataset_name, description):
		self.datasets[dataset_name] = MagicMock(id=dataset_name, description=description)
		return self.datasets[dataset_name]

	def create_examples(self, dataset_id, examples):
		self.examples = examples

	def evaluate(self, target, data, evaluators, **kwargs):
		self.metadata = kwargs.get("metadata")
		rows = []
		for example in self.examples:
			outputs = target(example["inputs"])
			results = [self._call(e, example, outputs) for e in evaluators]
			rows.append({"outputs": outputs, "evaluation_results": {"results": results}})
		self.rows = rows
		return MagicMock(__iter__=lambda s: iter(rows), experiment_name="exp")

	def read_project(self, project_name):
		return MagicMock(url="https://smith.example/exp")

	@staticmethod
	def _call(evaluator, example, outputs):
		kwargs = {"inputs": example["inputs"], "outputs": outputs, "reference_outputs": example["outputs"]}
		names = evaluator.__code__.co_varnames[: evaluator.__code__.co_argcount]
		return evaluator(**{k: v for k, v in kwargs.items() if k in names})


def judge():
	"""Fake evaluation model: answers openevals' structured-output call."""
	return fake_llm.fake_chat(
		*[fake_llm.tool_call("score", {"reasoning": "fine", "score": True}) for _ in range(10)]
	)


def target_model():
	return fake_llm.fake_chat(
		fake_llm.tool_call("count_documents", {"doctype": "ToDo"}),
		"You have 1 ToDo.",
		fake_llm.tool_call(
			"create_document", {"doctype": "ToDo", "values": {"description": "evaluation write"}}
		),
		"I proposed it; you rejected it.",
	)


class TestEvaluation(IntegrationTestCase):
	def setUp(self):
		self.eval_user = factories.assistant_user()
		factories.configure(
			langsmith_enabled=1, langsmith_api_key="lsv2_test_key_0000000000", evaluation_user=self.eval_user
		)
		self.admin = factories.assistant_user(roles=("System Manager",))
		self.langsmith = FakeLangSmith()
		tracing._clients.clear()
		patches = [
			patch.object(tracing, "_build_client", return_value=self.langsmith),
			patch.object(dataset, "load", return_value=EXAMPLES),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def run_eval(self, target="fake-main", model=None):
		models = {target: model or target_model(), "fake-eval": judge()}
		with fake_llm.use_models(chat=models), self.set_user(self.admin):
			name = settings_api.run_evaluation(target_model=target)
		return frappe.get_doc("AI Evaluation Run", name)

	def test_ac26_ac27_completed_with_scores_and_no_write(self):
		run = self.run_eval()
		self.assertEqual(run.status, "Completed", run.error)
		scores = frappe.parse_json(run.scores)
		self.assertEqual(scores["correctness"], 1)
		self.assertEqual(scores["write_confirmed"], 1)
		self.assertEqual(scores["tool_selection"], 1)
		self.assertTrue(run.passed)
		self.assertEqual(run.langsmith_experiment_url, "https://smith.example/exp")
		self.assertFalse(frappe.db.exists("ToDo", {"description": "evaluation write"}))
		proposed = self.langsmith.rows[1]["outputs"]["proposed_actions"]
		self.assertEqual(proposed[0]["operation"], "create")
		self.assertTrue(
			frappe.db.exists("AI Usage Log", {"purpose": "evaluation", "profile_id": "fake-eval"})
		)

	def test_ac28_refused_without_allow_tests_or_langsmith(self):
		with self.set_user(self.admin):
			with (
				patch.dict(frappe.conf, {"allow_tests": 0}),
				self.assertRaises(runner.EvaluationRefusedError),
			):
				settings_api.run_evaluation()
			factories.configure(langsmith_enabled=0, evaluation_user=self.eval_user)
			tracing._clients.clear()
			with self.assertRaises(runner.EvaluationRefusedError):
				settings_api.run_evaluation()

	def test_ac29_candidate_target(self):
		run = self.run_eval(target="fake-candidate")
		self.assertEqual(run.status, "Completed", run.error)
		self.assertEqual(settings.get().main_model, "fake-main")
		self.assertEqual(self.langsmith.metadata["target_model"], "fake-candidate")
		self.assertTrue(
			frappe.db.exists("AI Usage Log", {"purpose": "evaluation", "profile_id": "fake-candidate"})
		)

	def test_only_system_manager(self):
		with self.set_user(self.eval_user), self.assertRaises(frappe.PermissionError):
			settings_api.run_evaluation()
