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
"answer" is the index (0-3) of the correct option."""


def _words(grade: str) -> int:
	if grade.startswith("PP"):
		return 200
	n = cint(grade.split()[-1])
	return 300 if n <= 3 else 500 if n <= 6 else 700


def _scope(sub_strand: str) -> frappe._dict:
	sub = frappe.db.get_value("Sub-strand", sub_strand, ["name", "name1", "strand", "order"], as_dict=True)
	if not sub:
		frappe.throw(_("Sub-strand {0} not found.").format(sub_strand))
	strand = frappe.db.get_value("Strand", sub.strand, ["name", "strand_name", "subject"], as_dict=True)
	grade = frappe.db.get_value("Program Course", {"course": strand.subject, "parenttype": "Program"}, "parent")
	if not grade:
		frappe.throw(_("Add {0} to a grade (Program) before writing its lessons.").format(strand.subject))
	outcomes = frappe.get_all(
		"Learning Outcome",
		filters={"sub_strand": sub_strand},
		fields=["name", "description"],
		order_by="`order` asc",
	)
	return frappe._dict(sub=sub, strand=strand, grade=grade, outcomes=outcomes)


def _prompt(s: frappe._dict) -> str:
	outcomes = "\n".join(f"- {strip_html(cstr(o.description)).strip()}" for o in s.outcomes) or "- (none listed)"
	area = frappe.db.get_value("Course", s.strand.subject, "course_name") or s.strand.subject
	return LESSON_PROMPT.format(
		grade=s.grade,
		area=area,
		strand=s.strand.strand_name,
		sub_strand=s.sub.name1,
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
				"options": [{"option": o[:500], "is_correct": int(i == answer)} for i, o in enumerate(options)],
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


def write_lesson(sub_strand: str) -> str:
	"""Writes a lesson and its quiz for the sub-strand and returns the new Lesson's name."""
	s = _scope(sub_strand)
	reply = providers.complete(
		"You write accurate, engaging CBC lessons for Kenyan schools.",
		[{"role": "user", "content": _prompt(s)}],
		json_mode=True,
		max_tokens=4000,
	)
	data = providers.parse_json(reply["text"])
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
			"key_vocabulary": ", ".join(cstr(w).strip() for w in data.get("key_vocabulary") or [] if cstr(w).strip()),
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


def without_lessons(limit: int) -> list[str]:
	"""Active sub-strands that have no lesson yet, in curriculum order."""
	return frappe.db.sql_list(
		"""select ss.name from `tabSub-strand` ss
		where ifnull(ss.active, 1) = 1
			and not exists (select 1 from `tabLesson` l where l.sub_strand = ss.name)
		order by ss.strand, ss.`order`
		limit %s""",
		(limit,),
	)


def daily() -> None:
	"""Scheduled: write lessons for sub-strands that have none, a few a day."""
	per_day = cint(common.setting("ai_lessons_per_day", 0))
	if not per_day or not cint(common.setting("ai_enabled", 1)):
		return
	for name in without_lessons(per_day):
		try:
			write_lesson(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"CBC lesson for {name}")
