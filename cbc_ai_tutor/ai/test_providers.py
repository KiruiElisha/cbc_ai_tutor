"""The provider layer: the backup provider takes over, refusals stand, and Cursor answers without tools."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import cursor_sdk
import frappe

from cbc_ai_tutor.ai import providers

TURNS = [{"role": "user", "content": "What is a fraction?"}]


def _conf(provider="OpenAI", **extra):
	return frappe._dict(
		enabled=1,
		provider=provider,
		model="m",
		base_url="",
		key="k",
		temperature=0.4,
		max_tokens=100,
		timeout=5,
		**extra,
	)


class FakeRun:
	def __init__(self, result=None, error=None):
		self.result, self.error, self.cancelled = result, error, False

	def wait(self):
		if self.error:
			raise self.error
		return self.result

	def cancel(self):
		self.cancelled = True


class FakeAgent:
	def __init__(self, run):
		self.run, self.sent, self.closed = run, None, False

	def send(self, message):
		self.sent = message
		return self.run

	def close(self):
		self.closed = True


def _finished(text="A fraction is a part of a whole."):
	return SimpleNamespace(
		status="finished",
		result=text,
		usage=SimpleNamespace(input_tokens=40, output_tokens=12),
		error_code=None,
		error_message=None,
	)


class TestBackupProvider(unittest.TestCase):
	def test_the_backup_answers_when_the_main_provider_is_down(self):
		backup = _conf("Google Gemini")
		calls = []

		def ask(conf, *args):
			calls.append(conf.provider)
			if conf.provider == "Cursor":
				raise providers.AIUnavailable("down")
			return {"text": "hi", "provider": conf.provider, "model": conf.model}

		with (
			patch.object(providers, "_config", return_value=_conf("Cursor")),
			patch.object(providers, "_fallback", return_value=backup),
			patch.object(providers, "_ask", side_effect=ask),
		):
			reply = providers.complete("sys", TURNS)
		self.assertEqual(calls, ["Cursor", "Google Gemini"])
		self.assertEqual(reply["provider"], "Google Gemini")

	def test_a_safety_refusal_is_not_sent_to_the_backup(self):
		with (
			patch.object(providers, "_config", return_value=_conf()),
			patch.object(providers, "_fallback", return_value=_conf("Anthropic")) as fallback,
			patch.object(providers, "_ask", side_effect=providers.AIRefused("no")),
		):
			with self.assertRaises(providers.AIRefused):
				providers.complete("sys", TURNS)
		fallback.assert_not_called()

	def test_without_a_backup_the_main_providers_error_stands(self):
		with (
			patch.object(providers, "_config", return_value=_conf()),
			patch.object(providers, "_fallback", return_value=None),
			patch.object(providers, "_ask", side_effect=providers.AIUnavailable("down")),
		):
			with self.assertRaises(providers.AIUnavailable):
				providers.complete("sys", TURNS)


class TestCursor(unittest.TestCase):
	def _answer(self, run, conf=None):
		agent = FakeAgent(run)
		with (
			patch.object(cursor_sdk.Agent, "create", return_value=agent) as create,
			patch.object(frappe, "log_error"),
		):
			reply = providers._cursor(conf or _conf("Cursor"), "Be kind.", TURNS, False)
		return reply, agent, create.call_args.args[0]

	def test_the_reply_and_token_counts_come_back(self):
		reply, agent, _ = self._answer(FakeRun(_finished()))
		self.assertEqual(reply["text"], "A fraction is a part of a whole.")
		self.assertEqual((reply["input_tokens"], reply["output_tokens"]), (40, 12))
		self.assertTrue(agent.closed)

	def test_the_agent_gets_no_tools_and_a_throwaway_folder(self):
		_, agent, options = self._answer(FakeRun(_finished()))
		self.assertEqual(list(options.tools), [])
		self.assertEqual(list(options.local.setting_sources), [])
		self.assertFalse(os.path.exists(options.local.cwd))
		self.assertIn("<instructions>\nBe kind.\n</instructions>", agent.sent)
		self.assertIn("Learner: What is a fraction?", agent.sent)

	def test_a_rejected_key_says_so(self):
		run = FakeRun(error=cursor_sdk.AuthenticationError("bad key"))
		with self.assertRaises(providers.AIUnavailable) as caught:
			self._answer(run)
		self.assertIn("rejected the API key", str(caught.exception))

	def test_a_run_that_ends_in_error_is_unavailable(self):
		failed = SimpleNamespace(status="error", result="", usage=None, error_code="x", error_message="boom")
		with self.assertRaises(providers.AIUnavailable):
			self._answer(FakeRun(failed))

	def test_a_slow_run_is_cancelled_at_the_timeout(self):
		class Slow(FakeRun):
			def wait(self):
				import time

				time.sleep(3)
				return _finished()

		run = Slow()
		conf = _conf("Cursor")
		conf.timeout = 0.2
		with self.assertRaises(providers.AIUnavailable):
			with patch.object(cursor_sdk.Agent, "create", return_value=FakeAgent(run)):
				providers._ask(conf, "sys", TURNS, False)
		self.assertTrue(run.cancelled)

	def test_json_mode_asks_for_bare_json(self):
		prompt = providers._cursor_prompt("sys", TURNS, True)
		self.assertTrue(
			prompt.endswith("Reply with a single JSON object and nothing else: no code fence, no commentary.")
		)
