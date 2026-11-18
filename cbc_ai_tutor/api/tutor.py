"""The AI tutor: chat about a lesson, practice questions, and teacher drafts."""

from __future__ import annotations

import json
import secrets
import time

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, cstr, md_to_html, now_datetime, strip_html

from cbc_ai_tutor.ai import providers, reuse
from cbc_ai_tutor.api import common, sync

MAX_MESSAGE = 2000
HISTORY_TURNS = 8

# How the learner asked Mwalimu to answer this time (the mode buttons under the chat).
STYLES = {
	"hint": "This time give only one small hint that moves the learner forward. Do not solve it.",
	"steps": "This time walk through it step by step, one numbered step at a time, and check understanding at the end.",
	"simple": "This time explain it more simply, with very short sentences and one everyday Kenyan example.",
	"quiz": "This time ask the learner one question at a time to check they understand, and wait for the answer.",
	"check": "The learner is sharing their own answer or working. Say what is right, point to the first mistake if any, and let them fix it.",
	"kiswahili": "This time answer in simple Kiswahili.",
	"voice": "The learner is listening, not reading: answer in short spoken sentences, with no tables, symbols or Markdown.",
}

TUTOR_RULES = """You are Mwalimu, a friendly AI tutor for learners in Kenya following the Competency-Based Curriculum (CBC) set by KICD.

How you teach:
- Match the learner's grade. Short sentences and simple words for younger learners.
- Guide, don't just hand over answers. Ask a question back, give a hint, then show the method step by step. Give the final answer only after the learner has tried or asks for it again.
- For homework or assignments, help the learner understand and plan; never write the work for them to hand in.
- Use Kenyan examples: shillings (KES), matatus, shambas, local foods, counties, Kenyan names and places.
- Link to the CBC core competencies where it helps: communication, critical thinking, creativity, citizenship, digital literacy, learning to learn, self-efficacy.
- If the learner writes in Kiswahili, answer in Kiswahili. Otherwise answer in English.
- Use Markdown: short paragraphs, numbered steps, and LaTeX-free maths written plainly (e.g. 3/4, 2 x 5 = 10).
- Bold the key words. When you give a final answer, put it on its own line starting with **Answer:** (in Kiswahili, **Jibu:**). Number each step of a method, one step per number.
- Keep answers under 250 words unless the learner asks for more.

Safety:
- You are talking to a child. Stay on schoolwork and healthy learning.
- Never ask for or repeat personal details (full name, school, phone, address, photos).
- Refuse anything violent, sexual, hateful, dangerous or about self-harm. If a learner seems unsafe or upset, tell them kindly to talk to a parent, teacher or call Childline Kenya on 116 (free).
- If you are not sure of a fact, say so instead of guessing."""


def _context(student: str, lesson: str | None, sub_strand: str | None, learning_outcome: str | None) -> frappe._dict:
	scope = frappe.db.get_value("Student", student, ["first_name", "custom_grade"], as_dict=True)
	return _context_for(scope, lesson, sub_strand, learning_outcome)


def _context_for(scope, lesson: str | None, sub_strand: str | None, learning_outcome: str | None) -> frappe._dict:
	"""The lesson and curriculum around a question; `scope` has the grade (custom_grade)."""
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
	resting = quiet_until(student)
	if resting:
		raise common.QuotaExceeded(
			_("Mwalimu is resting until {0}. Your parent set quiet hours. Lessons and quizzes still work.").format(
				resting
			)
		)
	if quota:
		_require_quota(student)
	return ent


def quiet_until(student: str, now=None) -> str | None:
	"""When the parent's quiet hours (bedtime, say) are on now, the time they end, as HH:MM."""
	from frappe.utils import get_time, now_datetime

	start, end = frappe.db.get_value("Student", student, ["custom_quiet_from", "custom_quiet_to"]) or (None, None)
	if not start or not end:
		return None
	start, end = get_time(start), get_time(end)
	if start == end:
		return None
	at = (now or now_datetime()).time()
	# Quiet hours may run past midnight, e.g. 21:00 to 06:00.
	inside = start <= at < end if start < end else (at >= start or at < end)
	return end.strftime("%H:%M") if inside else None


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
	style: str | None = None,
	stream: str | None = None,
	image: str | None = None,
	assignment: str | None = None,
) -> dict:
	student = common.current_learner()
	work = _mwalimu_work(student, assignment)
	if work:
		sub_strand = sub_strand or work.sub_strand
		learning_outcome = learning_outcome or work.learning_outcome
	photo = _photo(image)
	message = cstr(message).strip() or (_("Please help me with this.") if photo else "")
	styles = [s for s in cstr(style).split(",") if s in STYLES]
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
	# A styled answer (a hint, Kiswahili, spoken) is not the shared answer to the plain question.
	# A spoken, photographed or assignment answer is the learner's own; any other first question,
	# styled or plain, can be shared (and may have been written ahead of time).
	shareable = not (history or photo or work or "voice" in styles)
	key = reuse.question_key(ctx.grade, scope, message, ",".join(styles) or None) if shareable else None
	cached = reuse.cached_answer(key)
	if cached:
		reply = {"text": _html_to_markdownish(cached), "provider": "cache", "model": "", "input_tokens": 0, "output_tokens": 0}
	else:
		_require_quota(student)
		system = _system_prompt(ctx)
		if styles:
			system += "\n\nHow to answer:\n" + "\n".join(f"- {STYLES[s]}" for s in styles)
		if photo:
			system += "\n\n" + PHOTO_RULES
		if work:
			system += "\n\n" + WORK_RULES.format(title=work.title, notes=strip_html(cstr(work.description))[:1500] or "-")
		reply = providers.complete(
			system,
			[*history, {"role": "user", "content": message}],
			on_text=_writer(student, stream),
			images=[{"mime": photo["mime"], "data": photo["data"]}] if photo else None,
			# Short, simple questions can go to a fast, cheap model; working and checking can't.
			light=len(message) < 160 and not photo and not {"steps", "check"} & set(styles),
		)

	doc = frappe.get_doc(
		{
			"doctype": "AI Tutor Interaction",
			"student": student,
			"date": now_datetime(),
			"topic": cstr(ctx.topic)[:140] or message[:140],
			"conversation": conversation,
			"question": ("📷 " if photo else "") + frappe.utils.escape_html(message),
			"ai_response": cached or md_to_html(reply["text"]),
			"linked_learning_outcome": ctx.outcome.name if ctx.outcome else None,
			"lesson": ctx.lesson,
			"assignment": work.name if work else None,
			"question_key": key,
			"source": "Cache" if cached else "AI",
			"provider": reply["provider"],
			"model": reply["model"],
			"input_tokens": reply["input_tokens"],
			"output_tokens": reply["output_tokens"],
		}
	)
	doc.insert(ignore_permissions=True)
	if photo:
		# Kept privately with the question, for the parent and teacher to see what was asked.
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"mwalimu-{doc.name}.{photo['ext']}",
				"attached_to_doctype": "AI Tutor Interaction",
				"attached_to_name": doc.name,
				"is_private": 1,
				"content": photo["bytes"],
			}
		).insert(ignore_permissions=True)
	return {
		"interaction": doc.name,
		"conversation": conversation,
		"answer": reply["text"],
		"quota": sync.ai_quota(student),
	}


WORK_RULES = """This chat is practice the learner's teacher set: "{title}". The teacher's notes:
{notes}
Run it as a short practice session on this topic: ask one question at a time, wait for the answer,
say what was right, and when something is wrong, give a hint and let the learner try again before
explaining. After about five questions, sum up what went well and what to practise."""


def _mwalimu_work(student: str, assignment: str | None):
	"""A teacher's "Mwalimu Practice" assignment this learner can see, or None."""
	if not assignment:
		return None
	scope = sync._learner_scope(student)
	if assignment not in {a.name for a in sync.visible_assignments(scope)}:
		frappe.throw(_("That work was not set for you."))
	work = frappe.db.get_value(
		"Assignment",
		assignment,
		["name", "title", "description", "assignment_type", "sub_strand", "learning_outcome"],
		as_dict=True,
	)
	return work if work and work.assignment_type == "Mwalimu Practice" else None


PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
PHOTO_MAX_BYTES = 4 * 1024 * 1024
PHOTO_RULES = (
	"The learner sent a photo of their schoolwork (a book page, worksheet or their own working). "
	"Read it carefully and help with what it shows, guiding rather than just giving answers. If you "
	"can't read part of it, say which part. If it shows a person or anything other than schoolwork, "
	"say kindly that you can only help with photos of schoolwork, and do not describe the person."
)


def _photo(image: str | None) -> dict | None:
	"""A photo sent with a question, as a data URL or bare base64: checked, and ready to send."""
	import base64
	import binascii

	if not image:
		return None
	mime = "image/jpeg"
	data = cstr(image).strip()
	if data.startswith("data:"):
		head, _sep, data = data.partition(",")
		mime = head[5:].split(";")[0].lower()
	if mime not in PHOTO_TYPES:
		frappe.throw(_("Send the photo as a JPEG, PNG or WebP picture."))
	try:
		raw = base64.b64decode(data, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("The photo could not be read. Take it again."))
	if len(raw) > PHOTO_MAX_BYTES:
		frappe.throw(_("The photo is too large. Take it again a little further away."))
	return {"mime": mime, "ext": PHOTO_TYPES[mime], "data": data, "bytes": raw}


STREAM_KEY = "cbc_tutor_stream:"
STREAM_SECONDS = 180
STREAM_EVERY = 0.25


def _stream_key(student: str, stream: str) -> str:
	return f"{STREAM_KEY}{student}:{cstr(stream)[:40]}"


def _writer(student: str, stream: str | None):
	"""Keeps the answer so far in the cache while it is written, for `partial` to hand out.
	At most four writes a second: the app asks about twice a second."""
	if not stream:
		return None
	key = _stream_key(student, stream)
	last = {"at": 0.0}

	def write(text: str):
		now = time.monotonic()
		if now - last["at"] < STREAM_EVERY:
			return
		last["at"] = now
		frappe.cache.set_value(key, text, expires_in_sec=STREAM_SECONDS)

	return write


@frappe.whitelist()
@rate_limit(limit=300, seconds=60)
def partial(stream: str) -> dict:
	"""The answer Mwalimu is writing right now for this learner's question, so the app can show
	it word by word while `ask` is still running."""
	student = common.current_learner()
	return {"text": frappe.cache.get_value(_stream_key(student, stream)) or ""}


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


# The questions behind a lesson's starter buttons in the app (screens/learner/Tutor.svelte), with
# how they are asked for: answered once ahead of time, then instant for every learner.
STARTERS = (
	("Explain this lesson simply", "simple"),
	("Give me an example from home (lesson: {title})", None),
	("Ask me questions to check I understand", "quiz"),
	("Nieleze somo hili kwa Kiswahili", "kiswahili"),
)


def prewrite_answers(limit: int | None = None) -> dict:
	"""Write answers to the starter questions of published lessons that have none yet, with the
	fast, cheap providers first. Each in its own transaction; stops after a few failures in a row."""
	limit = cint(common.setting("ai_prewrite_per_day", 40)) if limit is None else cint(limit)
	if limit <= 0 or not cint(common.setting("ai_enabled", 1)) or not cint(common.setting("ai_reuse_answers", 1)):
		return {"written": 0}
	written, failed = 0, 0
	for lesson in frappe.get_all(
		"Lesson", filters={"published": 1}, fields=["name", "title", "program"], order_by="modified desc", limit_page_length=500
	):
		ctx = None
		for question, style in STARTERS:
			if written >= limit:
				return {"written": written}
			message = question.format(title=lesson.title)
			key = reuse.question_key(lesson.program, lesson.name, message, style)
			if not key or reuse.cached_answer(key):
				continue
			try:
				ctx = ctx or _context_for(frappe._dict(custom_grade=lesson.program), lesson.name, None, None)
				system = _system_prompt(ctx)
				if style:
					system += "\n\nHow to answer:\n- " + STYLES[style]
				reply = providers.complete(system, [{"role": "user", "content": message}], light=True)
				frappe.get_doc(
					{
						"doctype": "CBC Shared Answer",
						"question_key": key,
						"lesson": lesson.name,
						"style": style,
						"answer": md_to_html(reply["text"]),
						"provider": reply["provider"],
						"model": reply["model"],
					}
				).insert(ignore_permissions=True)
				frappe.db.commit()
				written, failed = written + 1, 0
			except Exception:
				frappe.db.rollback()
				frappe.log_error(title=f"Mwalimu answer ahead of time for {lesson.name}")
				failed += 1
				if failed >= 3:
					return {"written": written}
	return {"written": written}
