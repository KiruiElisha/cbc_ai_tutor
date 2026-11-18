"""Lessons and quizzes written once per sub-strand, then read by every learner in the grade.

This is where AI saves the most: one call writes a lesson and its quiz, and every learner who
opens it afterwards costs nothing, works offline, and needs no tutor message. Lessons are saved
as drafts for a teacher to check, unless CBC Settings publishes them straight away.

From Desk, "Write lesson with AI" on a Sub-strand writes one now. The daily job fills the
sub-strands that have no lesson yet, a few a day (CBC Settings → Lessons written per day).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, md_to_html, strip_html

from cbc_ai_tutor.ai import providers
from cbc_ai_tutor.api import common

LESSON_PROMPT = """Write one lesson for Kenyan learners in {grade}, {area}, following the KICD Competency-Based Curriculum.

Strand: {strand}
Sub-strand: {sub_strand}
Topics to cover:
{scope}
Specific learning outcomes:
{outcomes}

Rules:
- Match {grade}: short sentences and familiar words for young learners, more depth for older ones.
- Teach through Kenyan everyday life: shillings, the shamba, the market, matatus, local foods, counties.
- Explain, give worked examples, then let the learner try. Accurate facts only; leave out anything you are unsure of.
- About {words} words in "body". Use Markdown headings, short paragraphs and lists. No images or links.
- 5 quiz questions that check understanding of this lesson, each with exactly 4 options and one correct.

Reply with JSON only, in exactly this shape:
{{"title": "...", "summary": "one or two sentences", "body": "markdown", "key_vocabulary": ["word", "..."],
"activities": "markdown: something to do at home or in class", "reflection": "one question to think about",
"minutes": 20, "quiz": [{{"question": "...", "options": ["...", "...", "...", "..."], "answer": 0}}]}}
"answer" is the index (0-3) of the correct option. Inside strings, write any double quote as \\"."""


def _words(grade: str) -> int:
	if grade.startswith("PP"):
		return 200
	n = cint(grade.split()[-1])
	return 300 if n <= 3 else 500 if n <= 6 else 700


def _scope(sub_strand: str) -> frappe._dict:
	sub = frappe.db.get_value(
		"Sub-strand", sub_strand, ["name", "name1", "strand", "order", "description"], as_dict=True
	)
	if not sub:
		frappe.throw(_("Sub-strand {0} not found.").format(sub_strand))
	strand = frappe.db.get_value("Strand", sub.strand, ["name", "strand_name", "subject"], as_dict=True)
	grade = frappe.db.get_value(
		"Program Course", {"course": strand.subject, "parenttype": "Program"}, "parent"
	)
	if not grade:
		frappe.throw(_("Add {0} to a grade (Program) before writing its lessons.").format(strand.subject))
	# Sorted here: Frappe 16 refuses the reserved word `order` in order_by.
	outcomes = sorted(
		frappe.get_all(
			"Learning Outcome", filters={"sub_strand": sub_strand}, fields=["name", "description", "order"]
		),
		key=lambda o: cint(o.order),
	)
	return frappe._dict(sub=sub, strand=strand, grade=grade, outcomes=outcomes)


def _prompt(s: frappe._dict) -> str:
	outcomes = (
		"\n".join(f"- {strip_html(cstr(o.description)).strip()}" for o in s.outcomes) or "- (none listed)"
	)
	area = frappe.db.get_value("Course", s.strand.subject, "course_name") or s.strand.subject
	return LESSON_PROMPT.format(
		grade=s.grade,
		area=area,
		strand=s.strand.strand_name,
		sub_strand=s.sub.name1,
		scope=strip_html(cstr(s.sub.description).replace("</li>", "\n")).strip() or "(as in the outcomes)",
		outcomes=outcomes,
		words=_words(s.grade),
	)


def _quiz(title: str, rows: list) -> str | None:
	"""Education Questions and a Quiz from the AI's rows; None when fewer than 3 are usable."""
	links = []
	for row in rows or []:
		options = [cstr(o).strip() for o in (row.get("options") or []) if cstr(o).strip()]
		answer = cint(row.get("answer"))
		text = cstr(row.get("question")).strip()
		if not text or len(options) != 4 or not 0 <= answer < 4:
			continue
		question = frappe.get_doc(
			{
				"doctype": "Question",
				"question": text[:1000],
				"question_type": "Single Correct Answer",
				"options": [
					{"option": o[:500], "is_correct": int(i == answer)} for i, o in enumerate(options)
				],
			}
		).insert(ignore_permissions=True)
		links.append({"question_link": question.name, "question": question.question})
	if len(links) < 3:
		return None
	name = title[:120]
	n = 2
	while frappe.db.exists("Quiz", name):
		name = f"{title[:115]} ({n})"
		n += 1
	return (
		frappe.get_doc(
			{
				"doctype": "Quiz",
				"title": name,
				"question": links,
				"passing_score": 60,
				"max_attempts": 0,
				"grading_basis": "Latest Highest Score",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _ask_for_lesson(prompt: str) -> dict:
	"""The lesson as JSON. A reply that isn't readable JSON is asked for once more, saying what was wrong."""
	system = "You write accurate, engaging CBC lessons for Kenyan schools."
	turns = [{"role": "user", "content": prompt}]
	reply = providers.complete(system, turns, json_mode=True, max_tokens=4000)
	try:
		return providers.parse_json(reply["text"])
	except providers.AIBadReply as e:
		retry = (
			f"{prompt}\n\nYour last reply was not valid JSON ({e.detail}). Reply again with valid JSON only: "
			'escape every double quote inside a string as \\" and close every string, list and object.'
		)
		turns = [{"role": "user", "content": retry}]
		reply = providers.complete(system, turns, json_mode=True, max_tokens=4000)
		return providers.parse_json(reply["text"])


def write_lesson(sub_strand: str) -> str:
	"""Writes a lesson and its quiz for the sub-strand and returns the new Lesson's name."""
	s = _scope(sub_strand)
	data = _ask_for_lesson(_prompt(s))
	title = cstr(data.get("title")).strip() or s.sub.name1
	body = cstr(data.get("body")).strip()
	if len(body) < 200:
		raise providers.AIUnavailable(_("The lesson came back too short. Try again."))
	quiz = _quiz(f"{title} ({s.grade})", data.get("quiz"))
	lesson = frappe.get_doc(
		{
			"doctype": "Lesson",
			"title": title[:140],
			"program": s.grade,
			"course": s.strand.subject,
			"strand": s.strand.name,
			"sub_strand": s.sub.name,
			"learning_outcome": s.outcomes[0].name if s.outcomes else None,
			"published": cint(common.setting("ai_lessons_publish", 0)),
			"lesson_order": cint(s.sub.order) * 10,
			"estimated_minutes": max(5, min(cint(data.get("minutes")) or 20, 60)),
			"summary": cstr(data.get("summary")).strip()[:500],
			"body": md_to_html(body),
			"key_vocabulary": ", ".join(
				cstr(w).strip() for w in data.get("key_vocabulary") or [] if cstr(w).strip()
			),
			"activities": md_to_html(cstr(data.get("activities"))),
			"reflection": cstr(data.get("reflection")).strip()[:500],
			"quiz": quiz,
		}
	)
	lesson.insert(ignore_permissions=True)
	return lesson.name


@frappe.whitelist(methods=["POST"])
def write_for(sub_strand: str) -> dict:
	"""Desk button on Sub-strand: write its lesson now."""
	frappe.only_for(("System Manager", "Academics User", "Instructor"))
	return {"lesson": write_lesson(sub_strand)}


def without_lessons(limit: int, grade: str | None = None) -> list[str]:
	"""Active sub-strands that have no lesson yet, in curriculum order, optionally for one grade."""
	in_grade = (
		"and st.subject in (select course from `tabProgram Course` where parent = %(grade)s)" if grade else ""
	)
	return frappe.db.sql_list(
		f"""select ss.name from `tabSub-strand` ss
		join `tabStrand` st on st.name = ss.strand
		where ifnull(ss.active, 1) = 1 {in_grade}
			and not exists (select 1 from `tabLesson` l where l.sub_strand = ss.name)
		order by st.subject, st.`order`, ss.`order`
		limit %(limit)s""",
		{"limit": limit, "grade": grade},
	)


def write_many(names: list[str]) -> None:
	"""Writes each lesson in its own transaction, so one failure does not undo the rest."""
	for name in names:
		try:
			write_lesson(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"CBC lesson for {name}")


@frappe.whitelist(methods=["POST"])
def write_grade(grade: str) -> dict:
	"""Desk button on a grade (Program): write every missing lesson there in the background."""
	frappe.only_for(("System Manager", "Academics User"))
	names = without_lessons(1000, grade)
	if names:
		frappe.enqueue(
			"cbc_ai_tutor.ai.content.write_many",
			names=names,
			queue="long",
			timeout=60 * 60 * 6,
			job_id=f"cbc-lessons-{grade}",
			deduplicate=True,
		)
	return {"queued": len(names)}


def daily() -> None:
	"""Scheduled: first the free lessons every learning area needs, then a few more a day.

	Both run on the long queue: a lesson takes a minute or more to write, longer than a
	scheduled job may run, and one job id each means a run still going is not started twice."""
	if not cint(common.setting("ai_enabled", 1)):
		return
	enqueue_free_lessons()
	frappe.enqueue(
		"cbc_ai_tutor.api.tutor.prewrite_answers",
		queue="long",
		timeout=60 * 60 * 3,
		job_id="cbc-prewrite-answers",
		deduplicate=True,
	)
	per_day = cint(common.setting("ai_lessons_per_day", 0))
	names = without_lessons(per_day) if per_day else []
	if names:
		frappe.enqueue(
			"cbc_ai_tutor.ai.content.write_many",
			names=names,
			queue="long",
			timeout=60 * 60 * 6,
			job_id="cbc-lessons-daily",
			deduplicate=True,
		)


# --- the free lessons: something to learn in every learning area, from the first sync ------------

FREE_PER_RUN = 40


def free_lessons_missing(limit: int = 1000) -> list[tuple[str, str | None, str]]:
	"""(sub_strand, draft lesson or None, grade) to publish so that every learning area of every grade has
	its `free_lessons_per_area` published lessons: the first topics in curriculum order that have
	none. A draft already written for a topic is published instead of being written again."""
	per_area = cint(common.setting("free_lessons_per_area", 2))
	if per_area <= 0:
		return []
	rows = frappe.db.sql(
		"""select pc.parent as grade, st.subject as course, ss.name as sub_strand,
			(select count(*) from `tabLesson` p where p.course = st.subject and p.program = pc.parent
				and p.published = 1) as published,
			(select l.name from `tabLesson` l where l.sub_strand = ss.name and l.program = pc.parent
				and l.published = 0 order by l.creation limit 1) as draft,
			exists(select 1 from `tabLesson` l where l.sub_strand = ss.name and l.program = pc.parent
				and l.published = 1) as has_published
		from `tabSub-strand` ss
		join `tabStrand` st on st.name = ss.strand
		join `tabProgram Course` pc on pc.course = st.subject and pc.parenttype = 'Program'
		where ifnull(ss.active, 1) = 1 and ifnull(st.active, 1) = 1
		order by pc.parent, st.subject, ifnull(st.`order`, 999999), ifnull(ss.`order`, 999999), ss.name""",
		as_dict=True,
	)
	out, wanted = [], {}
	for r in rows:
		key = (r.grade, r.course)
		if key not in wanted:
			wanted[key] = per_area - cint(r.published)
		if wanted[key] <= 0 or r.has_published:
			continue
		out.append((r.sub_strand, r.draft, r.grade))
		wanted[key] -= 1
		if len(out) >= limit:
			break
	return out


# Failures in a row before a run gives up: one slow lesson is skipped, a provider that is down
# or out of quota stops the run until tomorrow.
FAILURES_IN_A_ROW = 3


def write_free(limit: int = FREE_PER_RUN) -> dict:
	"""Write (or publish) the missing free lessons, each in its own transaction.

	A topic that gained a lesson since the list was made (another run, a teacher) is skipped,
	so nothing is written twice. A lesson the AI could not write is skipped too, and the run
	goes on; it stops after a few failures in a row, or at once when the key is rejected."""
	made, failed = 0, 0
	for sub_strand, draft, grade in free_lessons_missing(limit):
		if not draft and frappe.db.exists("Lesson", {"sub_strand": sub_strand, "program": grade}):
			continue
		try:
			name = draft or write_lesson(sub_strand)
			frappe.db.set_value("Lesson", name, {"published": 1, "is_free": 1})
			frappe.db.commit()
			made, failed = made + 1, 0
		except providers.AIUnavailable as e:
			frappe.db.rollback()
			failed += 1
			frappe.log_error(
				title=f"CBC free lesson for {sub_strand}: the AI could not write it",
				message=frappe.get_traceback(),
			)
			if failed >= FAILURES_IN_A_ROW or "api key" in str(e).lower():
				break
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"CBC free lesson for {sub_strand}")
	return {"written": made, "left": len(free_lessons_missing())}


def enqueue_free_lessons() -> None:
	"""After migrate and from Desk: the free lessons are written in the background."""
	if not cint(common.setting("ai_enabled", 1)) or not free_lessons_missing(1):
		return
	frappe.enqueue(
		"cbc_ai_tutor.ai.content.write_free",
		limit=1000,
		queue="long",
		timeout=60 * 60 * 6,
		job_id="cbc-free-lessons",
		deduplicate=True,
		enqueue_after_commit=True,
	)


@frappe.whitelist(methods=["POST"])
def write_free_lessons() -> dict:
	"""CBC Settings → Write free lessons now."""
	frappe.only_for(("System Manager", "Academics User"))
	missing = len(free_lessons_missing())
	if missing:
		enqueue_free_lessons()
	return {"queued": missing}
