"""One call shape over the AI providers CBC Settings can point at.

``complete`` takes a system prompt and a list of ``{"role": "user"|"assistant",
"content": str}`` turns and returns the reply text with token counts. The provider,
model, key and limits come from CBC Settings, so switching provider is a settings
change, not a code change.
"""

from __future__ import annotations

import json

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
	if not conf.model:
		raise AIUnavailable(_("The AI tutor has no model set yet."))
	if not conf.key and conf.provider != "OpenAI Compatible":
		raise AIUnavailable(_("The AI tutor is not set up yet."))
	return conf


def complete(system: str, messages: list[dict], *, json_mode: bool = False, max_tokens: int | None = None) -> dict:
	conf = _config()
	if max_tokens:
		conf.max_tokens = max_tokens
	handler = {
		"OpenAI": _openai,
		"OpenAI Compatible": _openai,
		"Anthropic": _anthropic,
		"Google Gemini": _gemini,
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


def _raise_for(response: requests.Response, provider: str):
	if response.ok:
		return
	body = response.text[:2000]
	frappe.log_error(title=f"AI provider {provider} returned {response.status_code}", message=body)
	if response.status_code in (401, 403):
		raise AIUnavailable(_("The AI provider rejected the API key. An administrator needs to check CBC Settings."))
	if response.status_code == 429:
		raise AIUnavailable(_("The tutor is busy. Try again in a minute."))
	if response.status_code == 400 and ("safety" in body.lower() or "content_filter" in body.lower()):
		raise AIUnavailable(_("The tutor can't help with that. Ask about your schoolwork."))
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
	text = "".join(block.get("text", "") for block in data.get("content") or [] if block.get("type") == "text")
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
		raise AIUnavailable(_("The tutor can't help with that. Ask about your schoolwork."))
	text = "".join(part.get("text", "") for part in (candidate.get("content") or {}).get("parts") or [])
	usage = data.get("usageMetadata") or {}
	return {
		"text": text.strip(),
		"input_tokens": cint(usage.get("promptTokenCount")),
		"output_tokens": cint(usage.get("candidatesTokenCount")),
		"stop": candidate.get("finishReason"),
	}


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
