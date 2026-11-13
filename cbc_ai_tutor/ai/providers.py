"""One call shape over the AI providers CBC Settings can point at.

``complete`` takes a system prompt and a list of ``{"role": "user"|"assistant",
"content": str}`` turns and returns the reply text with token counts. The provider,
model, key and limits come from CBC Settings, so switching provider is a settings
change, not a code change. A backup provider, when set, answers whenever the main one
is down, rejects the key or is out of quota, so learners still get a reply.

"Cursor" runs a Cursor agent through the Cursor SDK (``cursor-sdk``) with the key from
cursor.com/dashboard, billed to the Cursor plan. It is an agent runtime rather than a
chat API: each answer is one short agent run with no tools and no files.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading

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


class AIRefused(AIUnavailable):
	"""The model declined on safety grounds: asking another provider would not be right."""


def _config() -> frappe._dict:
	conf = frappe._dict(
		enabled=cint(common.setting("ai_enabled", 1)),
		provider=common.setting("ai_provider", "OpenAI"),
		model=(common.setting("ai_model") or "").strip(),
		base_url=(common.setting("ai_base_url") or "").strip().rstrip("/"),
		key=common.secret("ai_api_key"),
		temperature=flt(common.setting("ai_temperature", 0.4)),
		max_tokens=cint(common.setting("ai_max_output_tokens", 900)) or 900,
		timeout=cint(common.setting("ai_timeout_seconds", 60)) or 60,
	)
	if not conf.enabled:
		raise AIUnavailable(_("The AI tutor is switched off."))
	_check(conf)
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
	)
	try:
		_check(backup)
	except AIUnavailable:
		return None
	return backup


def complete(
	system: str, messages: list[dict], *, json_mode: bool = False, max_tokens: int | None = None
) -> dict:
	conf = _config()
	if max_tokens:
		conf.max_tokens = max_tokens
	try:
		return _ask(conf, system, messages, json_mode)
	except AIRefused:
		raise
	except AIUnavailable:
		backup = _fallback(conf)
		if not backup:
			raise
		return _ask(backup, system, messages, json_mode)


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
		frappe.log_error(title=f"AI provider {conf.provider} unreachable", message=frappe.get_traceback())
		raise AIUnavailable(_("The tutor can't be reached right now. Try again shortly."))
	result.update(provider=conf.provider, model=conf.model)
	if not (result.get("text") or "").strip():
		raise AIUnavailable(_("The tutor gave an empty answer. Try asking another way."))
	return result


@frappe.whitelist()
def check() -> dict:
	"""CBC Settings' "Check AI" button: one tiny question through the configured providers."""
	frappe.only_for("System Manager")
	reply = complete(
		"You are checking that an AI tutor works. Reply with one short friendly sentence.",
		[{"role": "user", "content": "Say hello to a Grade 4 learner."}],
		max_tokens=60,
	)
	return {"provider": reply["provider"], "model": reply["model"], "text": reply["text"][:300]}


def _raise_for(response: requests.Response, provider: str):
	if response.ok:
		return
	body = response.text[:2000]
	frappe.log_error(title=f"AI provider {provider} returned {response.status_code}", message=body)
	if response.status_code in (401, 403):
		raise AIUnavailable(
			_("The AI provider rejected the API key. An administrator needs to check CBC Settings.")
		)
	if response.status_code == 429:
		raise AIUnavailable(_("The tutor is busy. Try again in a minute."))
	if response.status_code == 400 and ("safety" in body.lower() or "content_filter" in body.lower()):
		raise AIRefused(_("The tutor can't help with that. Ask about your schoolwork."))
	raise AIUnavailable(_("The tutor ran into a problem. Try again."))


def _openai(conf, system, messages, json_mode):
	compatible = conf.provider == "OpenAI Compatible"
	base = conf.base_url or OPENAI_URL
	if compatible and not conf.base_url:
		raise AIUnavailable(_("The AI tutor's base URL is not set."))
	body = {
		"model": conf.model,
		"messages": [{"role": "system", "content": system}, *messages],
		"temperature": conf.temperature,
	}
	body["max_tokens" if compatible else "max_completion_tokens"] = conf.max_tokens
	if json_mode and not compatible:
		body["response_format"] = {"type": "json_object"}
	headers = {"Content-Type": "application/json"}
	if conf.key:
		headers["Authorization"] = f"Bearer {conf.key}"
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
	turns = _alternating(messages)
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
	generation = {"temperature": conf.temperature, "maxOutputTokens": conf.max_tokens}
	if json_mode:
		generation["responseMimeType"] = "application/json"
	body = {
		"systemInstruction": {"parts": [{"text": system}]},
		"contents": contents,
		"generationConfig": generation,
	}
	response = requests.post(
		GEMINI_URL.format(model=conf.model),
		json=body,
		headers={"x-goog-api-key": conf.key, "Content-Type": "application/json"},
		timeout=conf.timeout,
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
		frappe.log_error(
			title=f"Cursor run {result.status}",
			message=f"{result.error_code or ''} {result.error_message or ''}".strip() or result.status,
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

	frappe.log_error(title=f"Cursor: {type(error).__name__}", message=str(error)[:2000])
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
	"""JSON from a model reply, tolerating a ```json fence around it."""
	text = (text or "").strip()
	if text.startswith("```"):
		text = text.strip("`")
		if text.lower().startswith("json"):
			text = text[4:]
	start, end = text.find("{"), text.rfind("}")
	if start == -1 or end == -1:
		raise AIUnavailable(_("The tutor's answer could not be read. Try again."))
	try:
		return json.loads(text[start : end + 1])
	except ValueError:
		raise AIUnavailable(_("The tutor's answer could not be read. Try again."))
