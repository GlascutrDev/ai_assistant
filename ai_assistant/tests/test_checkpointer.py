import asyncio
from typing import TypedDict

from frappe.tests import IntegrationTestCase
from langgraph.checkpoint.conformance import checkpointer_test, validate
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from ai_assistant.persistence.checkpointer import FrappeCheckpointSaver


class State(TypedDict):
	value: str


def ask(state: State):
	answer = interrupt({"question": "approve?"})
	return {"value": f"{state['value']}:{answer}"}


def build(saver):
	graph = StateGraph(State)
	graph.add_node("ask", ask)
	graph.add_edge(START, "ask")
	graph.add_edge("ask", END)
	return graph.compile(checkpointer=saver)


class TestCheckpointer(IntegrationTestCase):
	def test_ac14_conformance_base(self):
		@checkpointer_test(name="FrappeCheckpointSaver")
		async def saver():
			yield FrappeCheckpointSaver()

		report = asyncio.run(validate(saver))
		self.assertTrue(report.passed_all_base(), report.to_dict() if hasattr(report, "to_dict") else report)

	def test_resume_with_new_saver_instance(self):
		config = {"configurable": {"thread_id": "test-resume-thread"}}
		first = build(FrappeCheckpointSaver())
		result = first.invoke({"value": "start"}, config)
		self.assertIn("__interrupt__", result)

		second = build(FrappeCheckpointSaver())
		result = second.invoke(Command(resume="yes"), config)
		self.assertEqual(result["value"], "start:yes")
