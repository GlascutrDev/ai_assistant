import io
import wave

import frappe
from frappe.tests import IntegrationTestCase

from ai_assistant.api import chat
from ai_assistant.services import conversations, voice
from ai_assistant.tests import factories, fake_llm


def wav_bytes(seconds: float, rate: int = 8000) -> bytes:
	out = io.BytesIO()
	with wave.open(out, "wb") as w:
		w.setnchannels(1)
		w.setsampwidth(2)
		w.setframerate(rate)
		w.writeframes(b"\x00\x00" * int(seconds * rate))
	return out.getvalue()


class TestVoice(IntegrationTestCase):
	def setUp(self):
		factories.configure(voice_enabled=1, max_voice_seconds=10)
		self.user = factories.assistant_user()

	def record(self, seconds: float = 2, text: str = "how many todos do i have"):
		with fake_llm.use_models(speech=text), self.set_user(self.user):
			conv = conversations.get_or_create(None)
			return voice.transcribe(conv, "recording.wav", wav_bytes(seconds))

	def test_ac30_transcribe_logs_attachment_and_usage(self):
		result = self.record()
		self.assertEqual(result["text"], "how many todos do i have")
		self.assertAlmostEqual(result["duration_seconds"], 2, places=1)
		att = frappe.get_doc("AI Attachment", result["attachment"])
		self.assertEqual((att.kind, att.status), ("voice", "Ready"))
		usage = frappe.get_all(
			"AI Usage Log",
			filters={"conversation": result["conversation"], "purpose": "transcription"},
			fields=["profile_id", "audio_seconds"],
		)
		self.assertEqual(usage[0].profile_id, "fake-speech")
		self.assertAlmostEqual(usage[0].audio_seconds, 2, places=1)

	def test_ac31_refused_when_disabled_or_too_long(self):
		with self.assertRaises(frappe.ValidationError):
			self.record(seconds=15)
		factories.configure(voice_enabled=0)
		with self.assertRaises(frappe.ValidationError):
			self.record()

	def test_ac32_voice_message_reaches_model_as_text(self):
		result = self.record(text="list my todos")
		model = fake_llm.fake_chat("Here they are.", "Title")
		with fake_llm.use_models(chat={"fake-main": model}), self.set_user(self.user):
			chat.send_message(
				text="list my todos please",
				conversation=result["conversation"],
				voice_attachment=result["attachment"],
			)
		message = frappe.get_all(
			"AI Message",
			filters={"conversation": result["conversation"], "role": "user"},
			fields=["input_mode", "content"],
		)[0]
		self.assertEqual((message.input_mode, message.content), ("voice", "list my todos please"))
		human = [m for m in model.calls[0] if m.type == "human"][-1]
		self.assertEqual(human.content, "list my todos please")

	def test_other_users_recording_refused(self):
		result = self.record()
		other = factories.assistant_user()
		with self.set_user(other):
			conv = conversations.get_or_create(None)
			with self.assertRaises(frappe.PermissionError):
				chat.send_message(text="hi", conversation=conv.name, voice_attachment=result["attachment"])
