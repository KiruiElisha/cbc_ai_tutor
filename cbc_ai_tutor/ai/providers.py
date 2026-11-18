"""One call shape over the AI providers CBC Settings can point at.

``complete`` takes a system prompt and a list of ``{"role": "user"|"assistant",
"content": str}`` turns and returns the reply text with token counts. The provider,
model, key and limits come from CBC Settings, so switching provider is a settings
change, not a code change. A backup provider, when set, answers whenever the main one
is down, rejects the key or is out of quota, so learners still get a reply.

More providers can be listed under "More AI providers", and CBC Settings' routing decides
how they share the work:

- Smart (default): the provider that has been answering fastest goes first; if it has not
  answered within a few seconds, the next one is asked as well and the first reply wins.
- Race: the two fastest are asked at once (fastest replies, about twice the cost).
- In order: the main provider, then the backup, then the list, one after another.

A provider that fails rests for a while (a minute when it is down, longer when it rejects
its key), so learners are not kept waiting on it. Response times and rests live in the
cache: nothing about them needs saving.

"Cursor" runs a Cursor agent through the Cursor SDK (``cursor-sdk``) with the key from
cursor.com/dashboard, billed to the Cursor plan. It is an agent runtime rather than a
chat API: each answer is one short agent run with no tools and no files.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import queue
import re
import tempfile
import threading
import time

import frappe
import requests
from frappe import _
from frappe.utils import cint, flt

from cbc_ai_tutor.api import common

OPENAI_URL = "https://api.openai.com/v1"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class AIUnavailable(frappe.ValidationError):
	http_status_code = 503


class AIBadReply(AIUnavailable):
	"""The model answered, but not in readable JSON; asking it again usually works."""

	def __init__(self, message: str, detail: str = ""):
		super().__init__(message)
		self.detail = detail


class AIRefused(AIUnavailable):
	"""The model declined on safety grounds: asking another provider would not be right."""


SMART, RACE, IN_ORDER = "Smart", "Race", "In order"
# Until a provider has answered a few times, how many seconds to expect from it. Cursor runs an
# agent for every answer, so it goes behind the chat APIs until it proves quicker.
EXPECTED_SECONDS = {"Cursor": 15.0}
DEFAULT_SECONDS = 5.0
REST_SECONDS = {"down": 60, "busy": 120, "key": 600}
STATS_KEY = "cbc_ai_provider_stats:"
STATS_DAYS = 7


def _config(require: bool = True) -> frappe._dict | None:
	"""The main provider. With `require=False`, None when it is not set up (the list may be)."""
	conf = frappe._dict(
		enabled=cint(common.setting("ai_enabled", 1)),
		provider=common.setting("ai_provider", "OpenAI"),
		model=(common.setting("ai_model") or "").strip(),
		base_url=(common.setting("ai_base_url") or "").strip().rstrip("/"),
		key=common.secret("ai_api_key"),
		temperature=flt(common.setting("ai_temperature", 0.4)),
		max_tokens=cint(common.setting("ai_max_output_tokens", 900)) or 900,
		timeout=cint(common.setting("ai_timeout_seconds", 60)) or 60,
		use_for="Everything",
	)
	if not conf.enabled:
		raise AIUnavailable(_("The AI tutor is switched off."))
	try:
		_check(conf)
	except AIUnavailable:
		if require:
			raise
		return None
	return conf


def _check(conf: frappe._dict):
	if not conf.model:
		raise AIUnavailable(_("The AI tutor has no model set yet."))
	if not conf.key and conf.provider != "OpenAI Compatible":
		raise AIUnavailable(_("The AI tutor is not set up yet."))


def _fallback(conf: frappe._dict) -> frappe._dict | None:
	"""The backup provider from CBC Settings, or None when there is none."""
	provider = common.setting("ai_fallback_provider")
	if not provider:
		return None
	backup = frappe._dict(
		conf,
		provider=provider,
		model=(common.setting("ai_fallback_model") or "").strip(),
		base_url=(common.setting("ai_fallback_base_url") or "").strip().rstrip("/"),
		key=common.secret("ai_fallback_api_key"),
		use_for="Everything",
	)
	try:
		_check(backup)
	except AIUnavailable:
		return None
	return backup


def _more_providers(base: frappe._dict) -> list[frappe._dict]:
	"""The enabled rows of "More AI providers", with the main provider's limits."""
	from frappe.utils.password import get_decrypted_password

	rows = frappe.get_all(
		"CBC AI Provider",
		filters={"parenttype": common.SETTINGS, "parentfield": "ai_providers", "enabled": 1},
		fields=[
			"name",
			"provider",
			"model",
			"base_url",
			"use_for",
			"daily_limit",
			"tier",
			"input_price",
			"output_price",
		],
		order_by="idx",
	)
	out = []
	for row in rows:
		conf = frappe._dict(
			base,
			provider=row.provider,
			model=(row.model or "").strip(),
			base_url=(row.base_url or "").strip().rstrip("/"),
			key=get_decrypted_password("CBC AI Provider", row.name, "api_key", raise_exception=False) or "",
			use_for=row.use_for or "Everything",
			daily_limit=cint(row.daily_limit),
			tier=row.tier or "Strong",
			input_price=flt(row.input_price),
			output_price=flt(row.output_price),
		)
		try:
			_check(conf)
		except AIUnavailable:
			continue
		out.append(conf)
	return out


def _pool(task: str) -> list[frappe._dict]:
	"""Every provider set up for this task: the main one, the backup, then the list."""
	main = _config(require=False)
	base = main or frappe._dict(_base_limits())
	pool = [main] if main else []
	backup = _fallback(base)
	if backup:
		pool.append(backup)
	pool += _more_providers(base)
	unwanted = "Lessons and questions only" if task == "chat" else "Chat only"
	pool = [conf for conf in pool if conf.get("use_for") != unwanted]
	seen, unique = set(), []
	for conf in pool:
		if _id(conf) not in seen:
			seen.add(_id(conf))
			unique.append(conf)
	if not unique:
		_config()  # says what is missing
		raise AIUnavailable(_("No AI provider is set up for this yet."))
	return unique


def _base_limits() -> dict:
	return dict(
		temperature=flt(common.setting("ai_temperature", 0.4)),
		max_tokens=cint(common.setting("ai_max_output_tokens", 900)) or 900,
		timeout=cint(common.setting("ai_timeout_seconds", 60)) or 60,
	)


# --- choosing who answers -------------------------------------------------------------------


def _id(conf: frappe._dict) -> str:
	raw = f"{conf.provider}|{conf.model}|{conf.get('base_url') or ''}"
	return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _today() -> str:
	return time.strftime("%Y-%m-%d")


def _stats(conf: frappe._dict) -> dict:
	return frappe.cache.get_value(STATS_KEY + _id(conf)) or {}


def _save_stats(conf: frappe._dict, stats: dict) -> None:
	frappe.cache.set_value(STATS_KEY + _id(conf), stats, expires_in_sec=STATS_DAYS * 86400)


def _record(conf: frappe._dict, seconds: float | None = None, error: Exception | None = None) -> None:
	"""Learn from an answer: its time, or a rest when it failed."""
	stats = _stats(conf)
	if stats.get("day") != _today():
		stats.update(day=_today(), used=0)
	if error is None:
		# Recent answers count most: a provider that gets slow loses its place within a few replies.
		avg = stats.get("avg")
		stats["avg"] = seconds if avg is None else round(avg * 0.7 + seconds * 0.3, 3)
		stats["n"] = stats.get("n", 0) + 1
		stats["fails"] = 0
		stats["used"] = stats.get("used", 0) + 1
		stats.pop("rest_until", None)
	elif not isinstance(error, AIRefused):
		stats["fails"] = stats.get("fails", 0) + 1
		text = str(error).lower()
		kind = "key" if "api key" in text else "busy" if "busy" in text else "down"
		# Each failure in a row rests it longer, up to ten times as long.
		stats["rest_until"] = time.time() + REST_SECONDS[kind] * min(stats["fails"], 10)
	_save_stats(conf, stats)


def _expected(conf: frappe._dict, stats: dict) -> float:
	expected = stats.get("avg") if stats.get("n") else None
	if expected is None:
		expected = EXPECTED_SECONDS.get(conf.provider, DEFAULT_SECONDS)
	return expected * (1 + 0.5 * stats.get("fails", 0))


def _ready(conf: frappe._dict, stats: dict) -> bool:
	if stats.get("rest_until", 0) > time.time():
		return False
	limit = cint(conf.get("daily_limit"))
	return not (limit and stats.get("day") == _today() and stats.get("used", 0) >= limit)


CHEAP = "Fast and cheap"


def _order(pool: list[frappe._dict], routing: str, light: bool | None = None) -> list[frappe._dict]:
	"""Ready providers first (fastest first, unless routing is "In order"); resting ones last,
	so they are still tried when nothing else answers.

	`light` True puts Fast and cheap providers ahead (a short, simple question), False puts Strong
	ones ahead (a lesson, or a question that needs working); None keeps speed alone."""
	stats = {_id(conf): _stats(conf) for conf in pool}
	ready = [conf for conf in pool if _ready(conf, stats[_id(conf)])]
	resting = [conf for conf in pool if conf not in ready]
	if routing != IN_ORDER:

		def rank(conf):
			cheap = conf.get("tier") == CHEAP
			tier = 0 if light is None or cheap == bool(light) else 1
			return (tier, _expected(conf, stats[_id(conf)]))

		ready.sort(key=rank)
	return ready + resting


def complete(
	system: str,
	messages: list[dict],
	*,
	json_mode: bool = False,
	max_tokens: int | None = None,
	on_text=None,
	images: list[dict] | None = None,
	light: bool | None = None,
) -> dict:
	"""The reply from whichever provider answers first, by CBC Settings' routing.

	`on_text(text)` receives the reply so far while it is written, for providers that stream
	(all but Cursor). When two providers are asked at once, only the first to write is shown."""
	task = "content" if json_mode else "chat"
	pool = _pool(task)
	if json_mode:
		# A lesson and its quiz take minutes to write; a learner's chat answer should not.
		wait = cint(common.setting("ai_content_timeout_seconds", 300)) or 300
		pool = [frappe._dict(conf, timeout=max(cint(conf.timeout), wait)) for conf in pool]
	if max_tokens:
		pool = [frappe._dict(conf, max_tokens=max_tokens) for conf in pool]
	if images:
		# A photo of the learner's work goes with their last message; Cursor can't read images.
		pool = [frappe._dict(conf, images=images) for conf in pool if conf.provider != "Cursor"]
		if not pool:
			raise AIUnavailable(
				_("Photo questions need an AI provider that reads images. Type the question instead.")
			)
	if on_text and not json_mode:
		pool = _sharing_one_writer(pool, on_text)
	routing = common.setting("ai_routing", SMART) or SMART
	order = _order(pool, routing, False if json_mode else light)
	if routing == IN_ORDER or len(order) == 1:
		return _one_after_another(order, system, messages, json_mode)
	wait = 0 if routing == RACE else max(flt(common.setting("ai_hedge_seconds", 6)), 1)
	return _overlapping(order, system, messages, json_mode, wait)


def _sharing_one_writer(pool: list[frappe._dict], on_text) -> list[frappe._dict]:
	"""Each provider gets its own on_text; the first one to write keeps the learner's screen."""
	lock = threading.Lock()
	state = {"writer": None}

	def for_provider(key):
		def write(text):
			with lock:
				if state["writer"] is None:
					state["writer"] = key
				mine = state["writer"] == key
			if mine:
				try:
					on_text(text)
				except Exception:
					pass  # showing progress must never break the answer

		return write

	return [frappe._dict(conf, on_text=for_provider(_id(conf))) for conf in pool]


def _timed(conf, system, messages, json_mode) -> dict:
	started = time.monotonic()
	try:
		result = _ask(conf, system, messages, json_mode)
	except Exception as e:
		_record(conf, error=e)
		raise
	_record(conf, seconds=time.monotonic() - started)
	return result


def _one_after_another(order, system, messages, json_mode) -> dict:
	error = None
	for conf in order:
		try:
			return _timed(conf, system, messages, json_mode)
		except AIRefused:
			raise
		except AIUnavailable as e:
			error = e
	raise error


_worker = threading.local()


def _log_error(title: str, message: str) -> None:
	"""Errors seen in a helper thread are kept for the request's own thread to save: two threads
	must not write through the one database connection."""
	logs = getattr(_worker, "logs", None)
	if logs is not None:
		logs.append((title, message))
	else:
		frappe.log_error(title=title, message=message)


def _overlapping(order, system, messages, json_mode, wait: float) -> dict:
	"""Ask the first provider; when it is slow (`wait` seconds) or fails, ask the next one too.
	The first reply wins. With `wait` 0 the first two are asked together."""
	results: queue.Queue = queue.Queue()
	logs: list = []

	def attempt(conf):
		_worker.logs = logs
		try:
			results.put((conf, _timed(conf, system, messages, json_mode), None))
		except Exception as e:
			results.put((conf, None, e))

	def launch(conf):
		# The thread sees this request's site and language, but keeps its own log list.
		context = contextvars.copy_context()
		threading.Thread(target=context.run, args=(attempt, conf), daemon=True).start()

	waiting, nxt, error = 0, 0, None
	deadline = time.monotonic() + max(cint(conf.timeout) for conf in order) + 5
	for _first in range(1 if wait else 2):
		if nxt < len(order):
			launch(order[nxt])
			nxt, waiting = nxt + 1, waiting + 1
	try:
		while waiting:
			left = deadline - time.monotonic()
			if left <= 0:
				break
			try:
				_conf, result, failure = results.get(
					timeout=min(wait, left) if wait and nxt < len(order) else left
				)
			except queue.Empty:
				if nxt < len(order):
					launch(order[nxt])
					nxt, waiting = nxt + 1, waiting + 1
				continue
			waiting -= 1
			if failure is None:
				return result
			if isinstance(failure, AIRefused):
				raise failure
			error = failure if isinstance(failure, AIUnavailable) else error or failure
			if nxt < len(order):
				launch(order[nxt])
				nxt, waiting = nxt + 1, waiting + 1
	finally:
		for title, message in list(logs):
			frappe.log_error(title=title, message=message)
	if error:
		raise error
	raise AIUnavailable(_("The tutor took too long to answer. Try again."))


def _ask(conf: frappe._dict, system: str, messages: list[dict], json_mode: bool) -> dict:
	handler = {
		"OpenAI": _openai,
		"OpenAI Compatible": _openai,
		"Anthropic": _anthropic,
		"Google Gemini": _gemini,
		"Cursor": _cursor,
	}.get(conf.provider)
	if not handler:
		raise AIUnavailable(_("Unknown AI provider {0}.").format(conf.provider))
	try:
		result = handler(conf, system, messages, json_mode)
	except requests.Timeout:
		raise AIUnavailable(_("The tutor took too long to answer. Try again."))
	except requests.RequestException:
		_log_error(f"AI provider {conf.provider} unreachable", frappe.get_traceback())
		raise AIUnavailable(_("The tutor can't be reached right now. Try again shortly."))
	result.update(provider=conf.provider, model=conf.model)
	if not (result.get("text") or "").strip():
		raise AIUnavailable(_("The tutor gave an empty answer. Try asking another way."))
	return result


@frappe.whitelist()
def check() -> dict:
	"""CBC Settings' "Check AI" button: the same tiny question to every provider at once, with
	how long each took. Their times also seed the routing."""
	frappe.only_for("System Manager")
	pool = []
	for task in ("chat", "content"):
		pool += [conf for conf in _pool(task) if _id(conf) not in {_id(c) for c in pool}]
	system = "You are checking that an AI tutor works. Reply with one short friendly sentence."
	turns = [{"role": "user", "content": "Say hello to a Grade 4 learner."}]
	results: queue.Queue = queue.Queue()
	logs: list = []

	def attempt(conf):
		_worker.logs = logs
		started = time.monotonic()
		try:
			reply = _timed(frappe._dict(conf, max_tokens=60), system, turns, False)
			results.put((conf, round(time.monotonic() - started, 1), reply["text"][:300], None))
		except Exception as e:
			results.put((conf, round(time.monotonic() - started, 1), "", str(e)[:300]))

	for conf in pool:
		threading.Thread(target=contextvars.copy_context().run, args=(attempt, conf), daemon=True).start()
	answers = []
	for _row in pool:
		try:
			conf, seconds, text, failure = results.get(timeout=max(cint(c.timeout) for c in pool) + 5)
		except queue.Empty:
			break
		answers.append(
			{
				"provider": conf.provider,
				"model": conf.model,
				"seconds": seconds,
				"text": text,
				"error": failure,
			}
		)
	for title, message in logs:
		frappe.log_error(title=title, message=message)
	answers.sort(key=lambda a: (bool(a["error"]), a["seconds"]))
	first = next((a for a in answers if not a["error"]), None)
	if not first:
		raise AIUnavailable(answers[0]["error"] if answers else _("No AI provider answered."))
	return {**first, "providers": answers}


def _raise_for(response: requests.Response, provider: str):
	if response.ok:
		return
	body = response.text[:2000]
	_log_error(f"AI provider {provider} returned {response.status_code}", body)
	if response.status_code in (401, 403):
		raise AIUnavailable(
			_("The AI provider rejected the API key. An administrator needs to check CBC Settings.")
		)
	if response.status_code == 429:
		raise AIUnavailable(_("The tutor is busy. Try again in a minute."))
	if response.status_code == 400 and ("safety" in body.lower() or "content_filter" in body.lower()):
		raise AIRefused(_("The tutor can't help with that. Ask about your schoolwork."))
	raise AIUnavailable(_("The tutor ran into a problem. Try again."))


def _sse(response: requests.Response):
	"""The JSON events of a server-sent-events stream."""
	response.encoding = "utf-8"
	for line in response.iter_lines(decode_unicode=True):
		if not line or not line.startswith("data:"):
			continue
		data = line[5:].strip()
		if data == "[DONE]":
			break
		try:
			yield json.loads(data)
		except json.JSONDecodeError:
			continue


def _last_user(turns: list[dict]) -> int:
	for i in range(len(turns) - 1, -1, -1):
		if turns[i]["role"] == "user":
			return i
	return -1


def _with_images(turns: list[dict], images, part) -> list[dict]:
	"""The turns with the photos added to the learner's last message, in the provider's shape:
	`part(image)` makes one image part, and text becomes the matching text part."""
	if not images:
		return turns
	turns = [dict(t) for t in turns]
	i = _last_user(turns)
	if i < 0:
		return turns
	text = turns[i]["content"]
	turns[i]["content"] = [*(part(image) for image in images), {"type": "text", "text": text}]
	return turns


def _streaming(conf, json_mode) -> bool:
	return bool(conf.get("on_text")) and not json_mode


def _openai(conf, system, messages, json_mode):
	compatible = conf.provider == "OpenAI Compatible"
	base = conf.base_url or OPENAI_URL
	if compatible and not conf.base_url:
		raise AIUnavailable(_("The AI tutor's base URL is not set."))
	turns = _with_images(
		list(messages),
		conf.get("images"),
		lambda image: {
			"type": "image_url",
			"image_url": {"url": f"data:{image['mime']};base64,{image['data']}"},
		},
	)
	body = {
		"model": conf.model,
		"messages": [{"role": "system", "content": system}, *turns],
		"temperature": conf.temperature,
	}
	body["max_tokens" if compatible else "max_completion_tokens"] = conf.max_tokens
	if json_mode and not compatible:
		body["response_format"] = {"type": "json_object"}
	headers = {"Content-Type": "application/json"}
	if conf.key:
		headers["Authorization"] = f"Bearer {conf.key}"
	if _streaming(conf, json_mode):
		body["stream"] = True
		if not compatible:
			body["stream_options"] = {"include_usage": True}
		response = requests.post(
			f"{base}/chat/completions", json=body, headers=headers, timeout=conf.timeout, stream=True
		)
		_raise_for(response, conf.provider)
		text, usage, stop = "", {}, None
		with response:
			for event in _sse(response):
				usage = event.get("usage") or usage
				for choice in (event.get("choices") or [])[:1]:
					piece = (choice.get("delta") or {}).get("content")
					if piece:
						text += piece
						conf.on_text(text)
					stop = choice.get("finish_reason") or stop
		return {
			"text": text.strip(),
			"input_tokens": cint(usage.get("prompt_tokens")),
			"output_tokens": cint(usage.get("completion_tokens")),
			"stop": stop,
		}
	response = requests.post(f"{base}/chat/completions", json=body, headers=headers, timeout=conf.timeout)
	_raise_for(response, conf.provider)
	data = response.json()
	choice = (data.get("choices") or [{}])[0]
	usage = data.get("usage") or {}
	return {
		"text": ((choice.get("message") or {}).get("content") or "").strip(),
		"input_tokens": cint(usage.get("prompt_tokens")),
		"output_tokens": cint(usage.get("completion_tokens")),
		"stop": choice.get("finish_reason"),
	}


def _anthropic(conf, system, messages, json_mode):
	turns = _with_images(
		_alternating(messages),
		conf.get("images"),
		lambda image: {
			"type": "image",
			"source": {"type": "base64", "media_type": image["mime"], "data": image["data"]},
		},
	)
	if json_mode:
		system += "\n\nReply with a single JSON object and nothing else."
	body = {
		"model": conf.model,
		"system": system,
		"messages": turns,
		"max_tokens": conf.max_tokens,
		"temperature": min(conf.temperature, 1.0),
	}
	headers = {
		"x-api-key": conf.key,
		"anthropic-version": ANTHROPIC_VERSION,
		"content-type": "application/json",
	}
	if _streaming(conf, json_mode):
		body["stream"] = True
		response = requests.post(ANTHROPIC_URL, json=body, headers=headers, timeout=conf.timeout, stream=True)
		_raise_for(response, conf.provider)
		text, tokens_in, tokens_out, stop = "", 0, 0, None
		with response:
			for event in _sse(response):
				kind = event.get("type")
				if kind == "message_start":
					tokens_in = cint(((event.get("message") or {}).get("usage") or {}).get("input_tokens"))
				elif kind == "content_block_delta":
					piece = (event.get("delta") or {}).get("text")
					if piece:
						text += piece
						conf.on_text(text)
				elif kind == "message_delta":
					stop = (event.get("delta") or {}).get("stop_reason") or stop
					tokens_out = cint((event.get("usage") or {}).get("output_tokens")) or tokens_out
				elif kind == "error":
					_log_error("Anthropic stream error", json.dumps(event)[:2000])
					raise AIUnavailable(_("The tutor ran into a problem. Try again."))
		return {"text": text.strip(), "input_tokens": tokens_in, "output_tokens": tokens_out, "stop": stop}
	response = requests.post(ANTHROPIC_URL, json=body, headers=headers, timeout=conf.timeout)
	_raise_for(response, conf.provider)
	data = response.json()
	text = "".join(
		block.get("text", "") for block in data.get("content") or [] if block.get("type") == "text"
	)
	usage = data.get("usage") or {}
	return {
		"text": text.strip(),
		"input_tokens": cint(usage.get("input_tokens")),
		"output_tokens": cint(usage.get("output_tokens")),
		"stop": data.get("stop_reason"),
	}


def _gemini(conf, system, messages, json_mode):
	contents = [
		{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
		for m in _alternating(messages)
	]
	if conf.get("images") and contents and contents[-1]["role"] == "user":
		contents[-1]["parts"] = [
			*({"inline_data": {"mime_type": i["mime"], "data": i["data"]}} for i in conf.images),
			*contents[-1]["parts"],
		]
	generation = {"temperature": conf.temperature, "maxOutputTokens": conf.max_tokens}
	if json_mode:
		generation["responseMimeType"] = "application/json"
	body = {
		"systemInstruction": {"parts": [{"text": system}]},
		"contents": contents,
		"generationConfig": generation,
	}
	headers = {"x-goog-api-key": conf.key, "Content-Type": "application/json"}
	if _streaming(conf, json_mode):
		url = GEMINI_URL.format(model=conf.model).replace(":generateContent", ":streamGenerateContent")
		response = requests.post(
			url, params={"alt": "sse"}, json=body, headers=headers, timeout=conf.timeout, stream=True
		)
		_raise_for(response, conf.provider)
		text, usage, stop = "", {}, None
		with response:
			for event in _sse(response):
				usage = event.get("usageMetadata") or usage
				for candidate in (event.get("candidates") or [])[:1]:
					stop = candidate.get("finishReason") or stop
					if stop == "SAFETY":
						raise AIRefused(_("The tutor can't help with that. Ask about your schoolwork."))
					piece = "".join(
						part.get("text", "") for part in (candidate.get("content") or {}).get("parts") or []
					)
					if piece:
						text += piece
						conf.on_text(text)
		return {
			"text": text.strip(),
			"input_tokens": cint(usage.get("promptTokenCount")),
			"output_tokens": cint(usage.get("candidatesTokenCount")),
			"stop": stop,
		}
	response = requests.post(
		GEMINI_URL.format(model=conf.model), json=body, headers=headers, timeout=conf.timeout
	)
	_raise_for(response, conf.provider)
	data = response.json()
	candidate = (data.get("candidates") or [{}])[0]
	if candidate.get("finishReason") == "SAFETY":
		raise AIRefused(_("The tutor can't help with that. Ask about your schoolwork."))
	text = "".join(part.get("text", "") for part in (candidate.get("content") or {}).get("parts") or [])
	usage = data.get("usageMetadata") or {}
	return {
		"text": text.strip(),
		"input_tokens": cint(usage.get("promptTokenCount")),
		"output_tokens": cint(usage.get("candidatesTokenCount")),
		"stop": candidate.get("finishReason"),
	}


CURSOR_BRIEF = (
	"You are answering inside the CBC AI Tutor app for Kenyan learners. This is not a coding task: "
	"use no tools, read or write no files, and do not mention code, files or Cursor. "
	"Follow the instructions below and write only the next reply to the learner."
)


def _cursor_prompt(system: str, messages: list[dict], json_mode: bool) -> str:
	"""Cursor agents take one message, so the instructions and the conversation go in it."""
	lines = [CURSOR_BRIEF, "", "<instructions>", system.strip(), "</instructions>", "", "<conversation>"]
	for message in _alternating(messages):
		who = "Tutor" if message["role"] == "assistant" else "Learner"
		lines.append(f"{who}: {message['content']}")
	lines.append("</conversation>")
	if json_mode:
		lines += ["", "Reply with a single JSON object and nothing else: no code fence, no commentary."]
	return "\n".join(lines)


def _cursor(conf, system, messages, json_mode):
	try:
		import cursor_sdk
	except ImportError:
		raise AIUnavailable(_("Cursor support is not installed on this server. Choose another AI provider."))
	errors = cursor_sdk.errors
	# An empty working folder and its own conversation store for each answer, removed afterwards,
	# so nothing about learners stays on disk and Cursor's user or project settings never apply.
	with tempfile.TemporaryDirectory(prefix="cbc-cursor-") as folder:
		options = cursor_sdk.AgentOptions(
			api_key=conf.key,
			model=conf.model,
			name="CBC AI Tutor",
			tools=[],  # no shell, no file edits: it only writes the answer
			local=cursor_sdk.LocalAgentOptions(
				cwd=folder,
				setting_sources=[],
				store=cursor_sdk.LocalAgentStoreConfig(type="jsonl", root_dir=os.path.join(folder, "store")),
			),
		)
		try:
			agent = cursor_sdk.Agent.create(options)
		except errors.CursorAgentError as e:
			_raise_for_cursor(e)
		try:
			run = agent.send(_cursor_prompt(system, messages, json_mode))
			outcome: dict = {}

			def wait():
				try:
					outcome["result"] = run.wait()
				except Exception as e:  # handed back to the request thread below
					outcome["error"] = e

			waiter = threading.Thread(target=wait, daemon=True)
			waiter.start()
			waiter.join(conf.timeout)
			if waiter.is_alive():
				try:
					run.cancel()
				except Exception:
					pass
				raise requests.Timeout()
			if "error" in outcome:
				error = outcome["error"]
				if isinstance(error, errors.CursorAgentError):
					_raise_for_cursor(error)
				raise error
		except errors.CursorAgentError as e:
			_raise_for_cursor(e)
		finally:
			try:
				agent.close()
			except Exception:
				pass
	result = outcome["result"]
	if result.status != "finished":
		_log_error(
			f"Cursor run {result.status}",
			f"{result.error_code or ''} {result.error_message or ''}".strip() or result.status,
		)
		raise AIUnavailable(_("The tutor ran into a problem. Try again."))
	usage = result.usage
	return {
		"text": (result.result or "").strip(),
		"input_tokens": cint(getattr(usage, "input_tokens", 0)),
		"output_tokens": cint(getattr(usage, "output_tokens", 0)),
		"stop": result.status,
	}


def _raise_for_cursor(error: Exception):
	import cursor_sdk.errors as errors

	_log_error(f"Cursor: {type(error).__name__}", str(error)[:2000])
	if isinstance(error, errors.AuthenticationError | errors.PermissionDeniedError):
		raise AIUnavailable(_("Cursor rejected the API key. An administrator needs to check CBC Settings."))
	if isinstance(error, errors.RateLimitError):
		raise AIUnavailable(_("The tutor is busy. Try again in a minute."))
	if isinstance(error, errors.APITimeoutError):
		raise AIUnavailable(_("The tutor took too long to answer. Try again."))
	if isinstance(error, errors.NetworkError | errors.InternalServerError):
		raise AIUnavailable(_("The tutor can't be reached right now. Try again shortly."))
	raise AIUnavailable(_("The tutor ran into a problem. Try again."))


def _alternating(messages: list[dict]) -> list[dict]:
	"""Anthropic and Gemini want strictly alternating turns that start with the user."""
	out: list[dict] = []
	for message in messages:
		role = "assistant" if message.get("role") == "assistant" else "user"
		content = (message.get("content") or "").strip()
		if not content:
			continue
		if out and out[-1]["role"] == role:
			out[-1]["content"] += "\n\n" + content
		else:
			out.append({"role": role, "content": content})
	while out and out[0]["role"] != "user":
		out.pop(0)
	return out


def parse_json(text: str) -> dict:
	"""JSON from a model reply, tolerating a ```json fence, raw newlines, trailing commas and
	unescaped double quotes inside strings (a Markdown lesson quoting someone is the usual one)."""
	text = (text or "").strip()
	if text.startswith("```"):
		text = text.strip("`")
		if text.lower().startswith("json"):
			text = text[4:]
	start, end = text.find("{"), text.rfind("}")
	if start == -1 or end == -1:
		raise AIBadReply(_("The tutor's answer could not be read. Try again."), "no JSON object in the reply")
	text = text[start : end + 1]
	try:
		return json.loads(text, strict=False)
	except json.JSONDecodeError as e:
		error = e
	try:
		data = json.loads(_repair_json(text), strict=False)
		if isinstance(data, dict):
			return data
	except json.JSONDecodeError:
		pass
	raise AIBadReply(
		_("The tutor's answer could not be read. Try again."), f"{error.msg} at character {error.pos}"
	)


_KEY_AHEAD = re.compile(r'"(?:[^"\\]|\\.)*"\s*:')
_SPACE = " \t\r\n"


def _skip_space(text: str, i: int) -> int:
	while i < len(text) and text[i] in _SPACE:
		i += 1
	return i


def _closes_string(text: str, i: int, is_key: bool, container: str) -> bool:
	"""Whether the quote at i ends the string: what follows must fit where the string stands."""
	j = _skip_space(text, i + 1)
	nxt = text[j] if j < len(text) else ""
	if is_key:
		return nxt == ":"
	if nxt in ("}", "]", ""):
		return True
	if nxt != ",":
		return False
	k = _skip_space(text, j + 1)
	if container == "{":
		return bool(_KEY_AHEAD.match(text, k)) or text[k : k + 1] == "}"
	return text[k : k + 1] != "" and text[k] in '"{[-0123456789tfn]'


def _repair_json(text: str) -> str:
	"""Escape the quotes a model left unescaped inside strings, and drop trailing commas.

	A quote closes a string only when what follows fits: a key is followed by ':', a value by
	'}' or ']', or by ',' and then the next key (in an object) or the next value (in a list).
	Any other quote is part of the text."""
	out, stack, last, i, n = [], [], "", 0, len(text)
	while i < n:
		c = text[i]
		if c == '"':
			container = stack[-1] if stack else ""
			is_key = container == "{" and last in "{,"
			out.append(c)
			i += 1
			while i < n:
				c = text[i]
				if c == "\\" and i + 1 < n:
					out.append(text[i : i + 2])
					i += 2
				elif c == '"' and _closes_string(text, i, is_key, container):
					out.append(c)
					i += 1
					break
				else:
					out.append('\\"' if c == '"' else c)
					i += 1
			last = '"'
			continue
		if c in "{[":
			stack.append(c)
		elif c in "}]" and stack:
			stack.pop()
		elif c == "," and text[_skip_space(text, i + 1) : _skip_space(text, i + 1) + 1] in ("}", "]"):
			i += 1
			continue
		if c not in _SPACE:
			last = c
		out.append(c)
		i += 1
	return "".join(out)


@frappe.whitelist()
def usage(days: int = 30) -> dict:
	"""CBC Settings' "AI usage": answers, tokens and cost by provider over the last `days`, and how
	each provider is doing now (its usual time, failures in a row, resting)."""
	frappe.only_for("System Manager")
	from frappe.utils import add_days, now_datetime

	days = min(max(cint(days), 1), 365)
	rows = frappe.db.sql(
		"""select coalesce(nullif(provider, ''), 'unknown') as provider, coalesce(model, '') as model,
			count(*) as answers, sum(input_tokens) as input_tokens, sum(output_tokens) as output_tokens,
			sum(source = 'Cache') as cached
		from `tabAI Tutor Interaction` where creation >= %s group by 1, 2 order by answers desc""",
		add_days(now_datetime(), -days),
		as_dict=True,
	)
	try:
		pool = []
		for task in ("chat", "content"):
			pool += [c for c in _pool(task) if _id(c) not in {_id(p) for p in pool}]
	except AIUnavailable:
		pool = []
	prices = {(c.provider, c.model): (flt(c.get("input_price")), flt(c.get("output_price"))) for c in pool}
	for row in rows:
		price_in, price_out = prices.get((row.provider, row.model), (0, 0))
		row["cost_usd"] = (
			round((flt(row.input_tokens) * price_in + flt(row.output_tokens) * price_out) / 1e6, 2)
			if price_in or price_out
			else None
		)
	now = []
	for conf in pool:
		stats = _stats(conf)
		now.append(
			{
				"provider": conf.provider,
				"model": conf.model,
				"tier": conf.get("tier") or "Strong",
				"seconds": stats.get("avg"),
				"answers_seen": stats.get("n", 0),
				"failures_in_a_row": stats.get("fails", 0),
				"resting": stats.get("rest_until", 0) > time.time(),
				"today": stats.get("used", 0) if stats.get("day") == _today() else 0,
			}
		)
	return {"days": days, "by_provider": rows, "now": now}
