"""The provider layer: the backup provider takes over, refusals stand, and Cursor answers without tools."""

import json
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


def _settings(**values):
	"""CBC Settings as the router reads them, with a cache of its own for response times."""
	stats: dict = {}
	return (
		patch.object(
			providers.common, "setting", side_effect=lambda field, default=None: values.get(field, default)
		),
		patch.object(providers, "_more_providers", return_value=[]),
		patch.object(providers, "_stats", side_effect=lambda conf: stats.setdefault(providers._id(conf), {})),
		patch.object(
			providers, "_save_stats", side_effect=lambda conf, s: stats.__setitem__(providers._id(conf), s)
		),
	)


class TestBackupProvider(unittest.TestCase):
	def _complete(self, main, backup, ask, routing="In order"):
		a, b, c, d = _settings(ai_routing=routing)
		with (
			a,
			b,
			c,
			d,
			patch.object(providers, "_config", return_value=main),
			patch.object(providers, "_fallback", return_value=backup) as fallback,
			patch.object(providers, "_ask", side_effect=ask),
		):
			return providers.complete("sys", TURNS), fallback

	def test_the_backup_answers_when_the_main_provider_is_down(self):
		calls = []

		def ask(conf, *args):
			calls.append(conf.provider)
			if conf.provider == "Cursor":
				raise providers.AIUnavailable("down")
			return {"text": "hi", "provider": conf.provider, "model": conf.model}

		reply, _ = self._complete(_conf("Cursor"), _conf("Google Gemini"), ask)
		self.assertEqual(calls, ["Cursor", "Google Gemini"])
		self.assertEqual(reply["provider"], "Google Gemini")

	def test_a_safety_refusal_is_not_sent_to_the_backup(self):
		calls = []

		def ask(conf, *args):
			calls.append(conf.provider)
			raise providers.AIRefused("no")

		with self.assertRaises(providers.AIRefused):
			self._complete(_conf(), _conf("Anthropic"), ask)
		self.assertEqual(calls, ["OpenAI"])

	def test_without_a_backup_the_main_providers_error_stands(self):
		with self.assertRaises(providers.AIUnavailable):
			self._complete(_conf(), None, providers.AIUnavailable("down"))


class TestRouting(unittest.TestCase):
	"""Several providers: the quickest answers, a slow one is overtaken, a failing one rests."""

	def _complete(self, pool, ask, **settings):
		a, b, c, d = _settings(**settings)
		with (
			a,
			b,
			c,
			d,
			patch.object(providers, "_config", return_value=pool[0]),
			patch.object(providers, "_fallback", return_value=pool[1] if len(pool) > 1 else None),
			patch.object(providers, "_ask", side_effect=ask),
		):
			return providers.complete("sys", TURNS), providers._order(
				pool, settings.get("ai_routing", "Smart")
			)

	def test_cursor_goes_behind_a_chat_api_until_it_proves_quicker(self):
		with patch.object(providers, "_stats", return_value={}):
			self.assertEqual(
				[c.provider for c in providers._order([_conf("Cursor"), _conf("Anthropic")], "Smart")],
				["Anthropic", "Cursor"],
			)

	def test_the_provider_that_has_answered_fastest_goes_first(self):
		stats = {
			providers._id(_conf("OpenAI")): {"avg": 4.0, "n": 5},
			providers._id(_conf("Google Gemini")): {"avg": 1.5, "n": 5},
		}
		with patch.object(providers, "_stats", side_effect=lambda conf: stats[providers._id(conf)]):
			order = providers._order([_conf("OpenAI"), _conf("Google Gemini")], "Smart")
		self.assertEqual([c.provider for c in order], ["Google Gemini", "OpenAI"])

	def test_a_slow_provider_is_overtaken_by_the_next_one(self):
		import time

		def ask(conf, *args):
			if conf.provider == "Anthropic":
				time.sleep(2)
			return {"text": conf.provider, "provider": conf.provider, "model": conf.model}

		started = time.monotonic()
		reply, _ = self._complete([_conf("Anthropic"), _conf("Google Gemini")], ask, ai_hedge_seconds=1)
		self.assertEqual(reply["provider"], "Google Gemini")
		self.assertLess(time.monotonic() - started, 1.9)

	def test_racing_asks_both_at_once_and_takes_the_first_reply(self):
		import time

		asked = []

		def ask(conf, *args):
			asked.append(conf.provider)
			time.sleep(0.3 if conf.provider == "Anthropic" else 0)
			return {"text": conf.provider, "provider": conf.provider, "model": conf.model}

		reply, _ = self._complete([_conf("Anthropic"), _conf("Google Gemini")], ask, ai_routing="Race")
		self.assertEqual(reply["provider"], "Google Gemini")
		time.sleep(0.4)
		self.assertEqual(sorted(asked), ["Anthropic", "Google Gemini"])

	def test_a_failing_provider_rests_and_the_next_answers_meanwhile(self):
		calls = []

		def ask(conf, *args):
			calls.append(conf.provider)
			if conf.provider == "Anthropic":
				raise providers.AIUnavailable("The tutor can't be reached right now.")
			return {"text": "ok", "provider": conf.provider, "model": conf.model}

		pool = [_conf("Anthropic"), _conf("Google Gemini")]
		a, b, c, d = _settings(ai_routing="In order")
		with a, b, c, d, patch.object(providers, "_ask", side_effect=ask):
			with (
				patch.object(providers, "_config", return_value=pool[0]),
				patch.object(providers, "_fallback", return_value=pool[1]),
			):
				providers.complete("sys", TURNS)
				calls.clear()
				reply = providers.complete("sys", TURNS)
		# Resting, Anthropic is passed over: the learner does not wait on it a second time.
		self.assertEqual(calls, ["Google Gemini"])
		self.assertEqual(reply["provider"], "Google Gemini")

	def test_a_provider_kept_for_lessons_does_not_answer_chat(self):
		lessons_only = _conf("Anthropic", use_for="Lessons and questions only")
		a, _b, c, d = _settings()
		with (
			a,
			c,
			d,
			patch.object(providers, "_config", return_value=_conf("OpenAI", use_for="Everything")),
			patch.object(providers, "_fallback", return_value=None),
			patch.object(providers, "_more_providers", return_value=[lessons_only]),
		):
			self.assertEqual([p.provider for p in providers._pool("chat")], ["OpenAI"])
			self.assertEqual([p.provider for p in providers._pool("content")], ["OpenAI", "Anthropic"])

	def test_a_provider_at_its_daily_limit_waits_until_tomorrow(self):
		capped = _conf("Anthropic", daily_limit=2)
		full = {"day": providers._today(), "used": 2, "avg": 0.5, "n": 3}
		with patch.object(providers, "_stats", side_effect=lambda conf: full if conf is capped else {}):
			order = providers._order([capped, _conf("OpenAI")], "Smart")
		self.assertEqual([c.provider for c in order], ["OpenAI", "Anthropic"])


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


class TestParseJson(unittest.TestCase):
	def test_quotes_the_model_left_unescaped_are_kept_as_text(self):
		body = 'Wanjiru said "Let us count" and pointed.\nThen "one", "two". Say "Habari!"'
		reply = (
			'```json\n{"title": "Counting", "body": "' + body + '", '
			'"quiz": [{"question": "Which is "big"?", "options": ["a", "b",], "answer": 0},],}\n```'
		)
		data = providers.parse_json(reply)
		self.assertEqual(data["body"], body)
		self.assertEqual(data["quiz"], [{"question": 'Which is "big"?', "options": ["a", "b"], "answer": 0}])

	def test_well_formed_json_is_read_as_it_is(self):
		self.assertEqual(
			providers.parse_json('{"body": "He said \\"hi\\", ok", "n": [1, "x"]}'),
			{"body": 'He said "hi", ok', "n": [1, "x"]},
		)

	def test_a_reply_cut_off_mid_lesson_says_what_was_wrong(self):
		with self.assertRaises(providers.AIBadReply) as caught:
			providers.parse_json('{"title": "Fractions", "body": "Half of 4 is }')
		self.assertIn("character", caught.exception.detail)


class FakeStream:
	"""A streamed HTTP reply: server-sent events, one `data:` line each."""

	def __init__(self, events):
		self.ok, self.status_code, self.text, self.encoding = True, 200, "", None
		self._lines = [f"data: {json.dumps(e)}" for e in events] + ["data: [DONE]"]

	def iter_lines(self, decode_unicode=True):
		yield from self._lines

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False


class TestStreaming(unittest.TestCase):
	"""The answer reaches the learner's screen while it is written, from every provider that streams."""

	def _stream(self, provider, events):
		seen = []
		conf = _conf(provider, on_text=seen.append)
		with patch.object(providers.requests, "post", return_value=FakeStream(events)) as post:
			reply = providers._ask(conf, "sys", TURNS, False)
		self.assertTrue(post.call_args.kwargs["stream"])
		return reply, seen

	def test_openai_sends_each_piece_and_counts_tokens(self):
		reply, seen = self._stream(
			"OpenAI",
			[
				{"choices": [{"delta": {"content": "A fraction "}}]},
				{"choices": [{"delta": {"content": "is a part."}, "finish_reason": "stop"}]},
				{"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 4}},
			],
		)
		self.assertEqual(seen, ["A fraction ", "A fraction is a part."])
		self.assertEqual(
			(reply["text"], reply["input_tokens"], reply["output_tokens"]), ("A fraction is a part.", 9, 4)
		)

	def test_anthropic_reads_its_own_event_types(self):
		reply, seen = self._stream(
			"Anthropic",
			[
				{"type": "message_start", "message": {"usage": {"input_tokens": 12}}},
				{"type": "content_block_delta", "delta": {"text": "Habari! "}},
				{"type": "content_block_delta", "delta": {"text": "Let us count."}},
				{
					"type": "message_delta",
					"delta": {"stop_reason": "end_turn"},
					"usage": {"output_tokens": 6},
				},
			],
		)
		self.assertEqual(seen[-1], "Habari! Let us count.")
		self.assertEqual((reply["input_tokens"], reply["output_tokens"], reply["stop"]), (12, 6, "end_turn"))

	def test_gemini_streams_and_a_safety_stop_is_a_refusal(self):
		reply, seen = self._stream(
			"Google Gemini",
			[
				{"candidates": [{"content": {"parts": [{"text": "Plants make "}]}}]},
				{
					"candidates": [{"content": {"parts": [{"text": "food."}]}, "finishReason": "STOP"}],
					"usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3},
				},
			],
		)
		self.assertEqual((seen[-1], reply["output_tokens"]), ("Plants make food.", 3))
		with self.assertRaises(providers.AIRefused):
			self._stream("Google Gemini", [{"candidates": [{"finishReason": "SAFETY"}]}])

	def test_lesson_writing_in_json_is_not_streamed(self):
		conf = _conf("OpenAI", on_text=lambda text: None)
		body = {"choices": [{"message": {"content": "{}"}}], "usage": {}}
		response = SimpleNamespace(ok=True, status_code=200, text="", json=lambda: body)
		with patch.object(providers.requests, "post", return_value=response) as post:
			providers._ask(conf, "sys", TURNS, True)
		self.assertNotIn("stream", post.call_args.kwargs)

	def test_only_the_first_provider_to_write_reaches_the_screen(self):
		seen = []
		first, second = providers._sharing_one_writer([_conf("OpenAI"), _conf("Anthropic")], seen.append)
		first.on_text("from OpenAI")
		second.on_text("from Anthropic")
		first.on_text("from OpenAI, more")
		self.assertEqual(seen, ["from OpenAI", "from OpenAI, more"])
