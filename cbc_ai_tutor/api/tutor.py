"""The AI tutor: chat about a lesson, practice questions, and teacher drafts."""

from __future__ import annotations

import json
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, cstr, md_to_html, now_datetime, strip_html

from cbc_ai_tutor.ai import providers, reuse
from cbc_ai_tutor.api import common, sync

MAX_MESSAGE = 2000
HISTORY_TURNS = 8

TUTOR_RULES = """You are Mwalimu, a friendly AI tutor for learners in Kenya following the Competency-Based Curriculum (CBC) set by KICD.

How you teach:
- Match the learner's grade. Short sentences and simple words for younger learners.
- Guide, don't just hand over answers. Ask a question back, give a hint, then show the method step by step. Give the final answer only after the learner has tried or asks for it again.
- For homework or assignments, help the learner understand and plan; never write the work for them to hand in.
- Use Kenyan examples: shillings (KES), matatus, shambas, local foods, counties, Kenyan names and places.
- Link to the CBC core competencies where it helps: communication, critical thinking, creativity, citizenship, digital literacy, learning to learn, self-efficacy.
- If the learner writes in Kiswahili, answer in Kiswahili. Otherwise answer in English.
- Use Markdown: short paragraphs, numbered steps, and LaTeX-free maths written plainly (e.g. 3/4, 2 x 5 = 10).
- Keep answers under 250 words unless the learner asks for more.

Safety:
- You are talking to a child. Stay on schoolwork and healthy learning.
- Never ask for or repeat personal details (full name, school, phone, address, photos).
- Refuse anything violent, sexual, hateful, dangerous or about self-harm. If a learner seems unsafe or upset, tell them kindly to talk to a parent, teacher or call Childline Kenya on 116 (free).
- If you are not sure of a fact, say so instead of guessing."""


def _context(student: str, lesson: str | None, sub_strand: str | None, learning_outcome: str | None) -> frappe._dict:
	scope = frappe.db.get_value("Student", student, ["first_name", "custom_grade"], as_dict=True)
	ctx = frappe._dict(grade=scope.custom_grade, first_name=scope.first_name, lesson=None, course=None,
		strand=None, sub_strand=None, outcome=None, lesson_text=None, topic=None)

	if lesson:
		row = frappe.db.get_value(
			"Lesson",
			lesson,
			["name", "title", "program", "course", "strand", "sub_strand", "learning_outcome", "summary", "body", "published", "is_free"],
			as_dict=True,
		)
		if not row or row.program != scope.custom_grade or not row.published:
			frappe.throw(_("That lesson is not part of your grade."))
		ctx.lesson = row.name
		ctx.topic = row.title
		ctx.course = row.course
		sub_strand = sub_strand or row.sub_strand
		learning_outcome = learning_outcome or row.learning_outcome
		ctx.strand = row.strand
		text = strip_html(cstr(row.summary) + "\n" + cstr(row.body))
		ctx.lesson_text = text[:2500]

	if learning_outcome:
		outcome = frappe.db.get_value("Learning Outcome", learning_outcome, ["name", "description", "sub_strand"], as_dict=True)
		if outcome:
			ctx.outcome = outcome
			sub_strand = sub_strand or outcome.sub_strand
	if sub_strand:
		sub = frappe.db.get_value("Sub-strand", sub_strand, ["name", "name1", "strand"], as_dict=True)
		if sub:
			ctx.sub_strand = sub
			ctx.strand = ctx.strand or sub.strand
			ctx.topic = ctx.topic or sub.name1
	if ctx.strand:
		strand = frappe.db.get_value("Strand", ctx.strand, ["strand_name", "subject"], as_dict=True)
		if strand:
			ctx.course = ctx.course or strand.subject
			ctx.strand_title = strand.strand_name
	return ctx


def _system_prompt(ctx: frappe._dict) -> str:
	lines = [TUTOR_RULES, "", "About this learner and lesson:"]
	lines.append(f"- Grade: {ctx.grade}")
	if ctx.course:
		lines.append(f"- Learning area: {ctx.course}")
	if ctx.get("strand_title"):
		lines.append(f"- Strand: {ctx.strand_title}")
	if ctx.sub_strand:
		lines.append(f"- Sub-strand: {ctx.sub_strand.name1}")
	if ctx.outcome:
		lines.append(f"- Learning outcome: {strip_html(cstr(ctx.outcome.description))[:500]}")
	if ctx.lesson_text:
		lines.append("- The lesson the learner is reading:\n\"\"\"\n" + ctx.lesson_text + "\n\"\"\"")
	extra = cstr(common.setting("ai_extra_instructions")).strip()
	if extra:
		lines += ["", "School instructions:", extra]
	return "\n".join(lines)


def _require_ai(student: str, quota: bool = True) -> frappe._dict:
	if not cint(common.setting("ai_enabled", 1)):
		raise providers.AIUnavailable(_("The AI tutor is switched off."))
	ent = common.entitlement_for_student(student)
	if not ent.active:
		raise common.SubscriptionRequired(_("The AI tutor needs an active subscription. Ask a parent to renew."))
	if quota:
		_require_quota(student)
	return ent


def _require_quota(student: str) -> None:
	"""Only answers that call the AI count; a shared, cached answer is free."""
	quota = sync.ai_quota(student)
	if quota["remaining"] is not None and quota["remaining"] <= 0:
		raise common.QuotaExceeded(
			_("You have used today's {0} tutor messages. They reset at midnight.").format(quota["limit"])
		)


def _history(student: str, conversation: str) -> list[dict]:
	rows = frappe.get_all(
		"AI Tutor Interaction",
		filters={"student": student, "conversation": conversation},
		fields=["question", "ai_response"],
		order_by="creation desc",
		limit_page_length=HISTORY_TURNS,
	)
	turns = []
	for row in reversed(rows):
		turns.append({"role": "user", "content": strip_html(cstr(row.question))})
		turns.append({"role": "assistant", "content": strip_html(cstr(row.ai_response))})
	return turns


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def ask(
	message: str,
	conversation: str | None = None,
	lesson: str | None = None,
	sub_strand: str | None = None,
	learning_outcome: str | None = None,
) -> dict:
	student = common.current_learner()
	message = cstr(message).strip()
	if not message:
		frappe.throw(_("Type a question first."))
	if len(message) > MAX_MESSAGE:
		frappe.throw(_("Keep your question under {0} characters.").format(MAX_MESSAGE))
	_require_ai(student, quota=False)

	if conversation:
		conversation = cstr(conversation)[:40]
		if not frappe.db.exists("AI Tutor Interaction", {"conversation": conversation, "student": student}):
			conversation = None
	conversation = conversation or secrets.token_hex(8)

	ctx = _context(student, lesson, sub_strand, learning_outcome)
	history = _history(student, conversation)
	# Only a first question is shared: a follow-up depends on the conversation before it.
	scope = ctx.lesson or (ctx.sub_strand or {}).get("name")
	key = None if history else reuse.question_key(ctx.grade, scope, message)
	cached = reuse.cached_answer(key)
	if cached:
		reply = {"text": _html_to_markdownish(cached), "provider": "cache", "model": "", "input_tokens": 0, "output_tokens": 0}
	else:
		_require_quota(student)
		reply = providers.complete(_system_prompt(ctx), [*history, {"role": "user", "content": message}])

	doc = frappe.get_doc(
		{
			"doctype": "AI Tutor Interaction",
			"student": student,
			"date": now_datetime(),
			"topic": cstr(ctx.topic)[:140] or message[:140],
			"conversation": conversation,
			"question": frappe.utils.escape_html(message),
			"ai_response": cached or md_to_html(reply["text"]),
			"linked_learning_outcome": ctx.outcome.name if ctx.outcome else None,
			"lesson": ctx.lesson,
			"question_key": key,
			"source": "Cache" if cached else "AI",
			"provider": reply["provider"],
			"model": reply["model"],
			"input_tokens": reply["input_tokens"],
			"output_tokens": reply["output_tokens"],
		}
	)
	doc.insert(ignore_permissions=True)
	return {
		"interaction": doc.name,
		"conversation": conversation,
		"answer": reply["text"],
		"quota": sync.ai_quota(student),
	}


@frappe.whitelist()
def conversations(limit: int = 30) -> list[dict]:
	student = common.current_learner()
	rows = frappe.db.sql(
		"""
		select conversation, min(creation) as started, max(creation) as last,
			count(*) as messages,
			substring_index(group_concat(topic order by creation separator '\x1f'), '\x1f', 1) as topic,
			substring_index(group_concat(lesson order by creation separator '\x1f'), '\x1f', 1) as lesson
		from `tabAI Tutor Interaction`
		where student = %s and ifnull(conversation, '') != ''
		group by conversation
		order by last desc
		limit %s
		""",
		(student, common.paginate(limit, 30, 100)),
		as_dict=True,
	)
	return [{**r, "started": str(r.started), "last": str(r.last)} for r in rows]


@frappe.whitelist()
def conversation(conversation: str) -> list[dict]:
	student = common.current_learner()
	rows = frappe.get_all(
		"AI Tutor Interaction",
		filters={"student": student, "conversation": conversation},
		fields=["name", "question", "ai_response", "creation", "feedback"],
		order_by="creation asc",
		limit_page_length=200,
	)
	return [
		{
			"interaction": r.name,
			"question": strip_html(cstr(r.question)),
			"answer": _html_to_markdownish(cstr(r.ai_response)),
			"at": str(r.creation),
			"feedback": r.feedback,
		}
		for r in rows
	]


def _html_to_markdownish(html: str) -> str:
	"""Stored replies are HTML for Desk; the app renders Markdown. Good enough to reread."""
	from frappe.core.utils import html2text

	try:
		return html2text(html).strip()
	except Exception:
		return strip_html(html)


PRACTICE_PROMPT = """Write {count} multiple-choice practice questions for this learner.

Rules:
- Each question has exactly 4 options and exactly one correct option.
- Questions test understanding, not memorised wording. Mix easy and harder ones.
- Use Kenyan contexts and the learner's grade level.
- Give a one or two sentence explanation for each answer, written to the learner.

Reply with JSON only, in exactly this shape:
{{"title": "short title", "questions": [{{"question": "...", "options": ["...", "...", "...", "..."], "answer": 0, "explanation": "..."}}]}}
"answer" is the index (0-3) of the correct option."""


def _write_practice(ctx: frappe._dict, count: int) -> tuple[dict, dict, list[dict]]:
	"""New questions from the AI, checked for shape. Shared afterwards through the topic pool."""
	reply = providers.complete(
		_system_prompt(ctx),
		[{"role": "user", "content": PRACTICE_PROMPT.format(count=count)}],
		json_mode=True,
		max_tokens=max(1200, count * 220),
	)
	data = providers.parse_json(reply["text"])
	questions = []
	for item in data.get("questions") or []:
		options = [cstr(o).strip() for o in (item.get("options") or []) if cstr(o).strip()]
		answer = cint(item.get("answer"))
		question = cstr(item.get("question")).strip()
		if question and len(options) == 4 and 0 <= answer < 4:
			questions.append(
				{
					"question": question[:600],
					"options": [o[:300] for o in options],
					"answer": answer,
					"explanation": cstr(item.get("explanation")).strip()[:600],
				}
			)
	if len(questions) < 2:
		raise providers.AIUnavailable(_("The tutor couldn't write good questions this time. Try again."))
	return reply, data, questions


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=10, seconds=60)
def practice(
	lesson: str | None = None,
	sub_strand: str | None = None,
	learning_outcome: str | None = None,
	count: int = 5,
) -> dict:
	"""AI-written practice questions. Counts as one tutor message."""
	student = common.current_learner()
	_require_ai(student, quota=False)
	if not (lesson or sub_strand or learning_outcome):
		frappe.throw(_("Pick a lesson or topic to practise."))
	count = max(3, min(cint(count) or 5, 10))
	ctx = _context(student, lesson, sub_strand, learning_outcome)
	key = reuse.topic_key(ctx.grade, ctx.lesson, (ctx.sub_strand or {}).get("name"), (ctx.outcome or {}).get("name"))
	questions = reuse.pooled_practice(key, count, student)
	reply, data = None, {}
	if not questions:
		_require_quota(student)
		reply, data, questions = _write_practice(ctx, count)

	grade = ctx.grade
	doc = frappe.get_doc(
		{
			"doctype": "Practice Questions",
			"student": student,
			"questions": json.dumps(questions),
			"question_type": "Multiple Choice",
			"subject": cstr(ctx.course)[:140],
			"grade_level": grade,
			"topic": (cstr(data.get("title")) or cstr(ctx.topic))[:140],
			"topic_key": key,
			"source": "AI" if reply else "Cache",
		}
	)
	doc.insert(ignore_permissions=True)
	if not reply:
		return {"practice": doc.name, "title": doc.topic, "questions": questions, "quota": sync.ai_quota(student)}

	frappe.get_doc(
		{
			"doctype": "AI Tutor Interaction",
			"student": student,
			"date": now_datetime(),
			"topic": doc.topic,
			"question": _("Practice questions ({0})").format(len(questions)),
			"ai_response": _("Practice set {0}").format(doc.name),
			"linked_learning_outcome": ctx.outcome.name if ctx.outcome else None,
			"lesson": ctx.lesson,
			"provider": reply["provider"],
			"model": reply["model"],
			"input_tokens": reply["input_tokens"],
			"output_tokens": reply["output_tokens"],
		}
	).insert(ignore_permissions=True)

	return {
		"practice": doc.name,
		"title": doc.topic,
		"questions": questions,
		"quota": sync.ai_quota(student),
	}


def grade_practice_for(student: str, practice: str, answers: list) -> dict:
	row = frappe.db.get_value("Practice Questions", practice, ["name", "student", "questions"], as_dict=True)
	if not row or row.student != student:
		raise sync.SyncRejected("not_found", _("That practice set is not yours."))
	questions = json.loads(row.questions or "[]")
	picked = [cint(a) if a not in (None, "") else -1 for a in (answers or [])][: len(questions)]
	picked += [-1] * (len(questions) - len(picked))
	correct = sum(1 for q, a in zip(questions, picked) if cint(q.get("answer")) == a)
	feedback = [
		{"correct": cint(q.get("answer")) == a, "answer": cint(q.get("answer")), "explanation": q.get("explanation")}
		for q, a in zip(questions, picked)
	]
	frappe.db.set_value(
		"Practice Questions",
		practice,
		{
			"score": f"{correct}/{len(questions)}",
			"student_answers": json.dumps(picked),
			"ai_feedback": json.dumps(feedback),
		},
	)
	return {"doctype": "Practice Questions", "name": practice, "score": correct, "total": len(questions), "feedback": feedback}


@frappe.whitelist(methods=["POST"])
def grade_practice(practice: str, answers) -> dict:
	student = common.current_learner()
	if isinstance(answers, str):
		answers = json.loads(answers or "[]")
	return grade_practice_for(student, practice, answers)


DRAFT_PROMPT = """Draft a {kind} for {grade} {area}{topic}.

Teacher's notes: {notes}

Write it for Kenyan CBC classrooms. Include:
1. A clear task the learners can follow on their own.
2. What they should hand in.
3. A simple rubric with the four CBC levels: Exceeding Expectations, Meeting Expectations, Approaching Expectations, Below Expectations.

Reply with JSON only: {{"title": "...", "description": "Markdown text of the task, hand-in and rubric"}}"""


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=60 * 60)
def draft_assignment(
	grade: str,
	learning_area: str | None = None,
	sub_strand: str | None = None,
	learning_outcome: str | None = None,
	kind: str = "Assignment",
	notes: str | None = None,
) -> dict:
	"""A first draft of an assignment for a teacher to edit. Not saved."""
	common.current_teacher()
	topic = ""
	if learning_outcome:
		topic = " on: " + strip_html(cstr(frappe.db.get_value("Learning Outcome", learning_outcome, "description")))[:400]
	elif sub_strand:
		topic = " on: " + cstr(frappe.db.get_value("Sub-strand", sub_strand, "name1"))
	prompt = DRAFT_PROMPT.format(
		kind=cstr(kind).lower() or "assignment",
		grade=grade,
		area=cstr(learning_area),
		topic=topic,
		notes=cstr(notes).strip()[:1000] or "none",
	)
	reply = providers.complete(
		"You help Kenyan CBC teachers prepare classwork. Be practical, age-appropriate and concise.",
		[{"role": "user", "content": prompt}],
		json_mode=True,
		max_tokens=1400,
	)
	data = providers.parse_json(reply["text"])
	return {"title": cstr(data.get("title"))[:140], "description": cstr(data.get("description"))}
