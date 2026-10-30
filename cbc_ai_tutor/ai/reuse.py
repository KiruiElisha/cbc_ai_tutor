"""Answers and practice questions written once and shared, so each AI call serves many learners.

A first question about a lesson ("what is evaporation?") is asked by many learners in the
same grade. The first one goes to the AI; later ones get that answer back from here, with no
AI call and no use of the learner's daily limit. Practice sets work the same way: questions
already written for a topic are drawn again before new ones are asked for.

Follow-up questions in a conversation are never reused, because they depend on what came
before. Answers a learner marked unhelpful are not reused either.
"""

from __future__ import annotations

import json
import random
import re

import frappe
from frappe.utils import add_days, cint, now_datetime

from cbc_ai_tutor.api import common

_FILLER = re.compile(
	r"\b(please|pls|plz|mwalimu|teacher|hi|hello|hey|habari|jambo|can you|could you|tell me|"
	r"explain to me|i want to know|i dont understand|i don't understand|kindly|tafadhali)\b"
)


def normalize(text: str) -> str:
	"""The question without greetings, punctuation or spacing, so small differences still match."""
	text = (text or "").lower()
	text = _FILLER.sub(" ", text)
	text = re.sub(r"[^\w\s]", " ", text)
	return re.sub(r"\s+", " ", text).strip()


def question_key(grade: str, scope: str | None, message: str) -> str | None:
	"""Grade, lesson or sub-strand, and the normalized question; None when too short to match safely."""
	words = normalize(message)
	if len(words) < 6:
		return None
	return f"{grade}|{scope or '-'}|{words}"[:140]


def cached_answer(key: str | None) -> str | None:
	"""The HTML of an earlier AI answer to the same question, if one is recent and was not marked unhelpful."""
	if not key or not cint(common.setting("ai_reuse_answers", 1)):
		return None
	days = cint(common.setting("ai_reuse_days", 90)) or 90
	rows = frappe.get_all(
		"AI Tutor Interaction",
		filters={
			"question_key": key,
			"source": "AI",
			"creation": [">=", add_days(now_datetime(), -days)],
		},
		fields=["ai_response", "feedback"],
		order_by="creation desc",
		limit_page_length=5,
	)
	for row in rows:
		if row.ai_response and "unhelpful" not in (row.feedback or "").lower():
			return row.ai_response
	return None


def topic_key(grade: str, lesson: str | None, sub_strand: str | None, outcome: str | None) -> str:
	return f"{grade}|{lesson or sub_strand or outcome or '-'}"[:140]


def pooled_practice(key: str, count: int, student: str) -> list[dict] | None:
	"""`count` questions already written for this topic, preferring ones the learner has not seen."""
	if not cint(common.setting("ai_reuse_answers", 1)):
		return None
	rows = frappe.get_all(
		"Practice Questions",
		filters={"topic_key": key},
		fields=["student", "questions"],
		order_by="creation desc",
		limit_page_length=200,
	)
	pool, seen = {}, set()
	for row in rows:
		for q in json.loads(row.questions or "[]"):
			text = normalize(q.get("question"))
			if not text:
				continue
			if row.student == student:
				seen.add(text)
			pool.setdefault(text, q)
	fresh = [q for text, q in pool.items() if text not in seen]
	if len(fresh) < count:
		return None
	return random.sample(fresh, count)
