"""The CBC structure, shaped the way the apps store it.

Grade (Program) → Learning Area (Course, listed on the Program) → Strand →
Sub-strand → Learning Outcome → Performance Indicator, with Lessons hanging off a
grade and learning area and, usually, a sub-strand and outcome.
"""

from __future__ import annotations

import re

import frappe
from frappe.utils import cint, cstr

LESSON_FIELDS = [
	"name",
	"title",
	"program",
	"course",
	"strand",
	"sub_strand",
	"learning_outcome",
	"lesson_order",
	"estimated_minutes",
	"is_free",
	"published",
	"quiz",
	"summary",
	"body",
	"key_vocabulary",
	"activities",
	"reflection",
	"image",
	"video_url",
	"modified",
]

LOCKED_FIELDS = ("body", "activities", "reflection", "key_vocabulary", "video_url", "quiz")


@frappe.whitelist(allow_guest=True)
def grades() -> list[dict]:
	"""Grades a family can pick, in CBC order (PP1, PP2, Grade 1 … Grade 12)."""
	rows = frappe.get_all("Program", fields=["name", "program_name", "program_abbreviation"], limit_page_length=0)
	return sorted(rows, key=lambda r: grade_sort_key(r.name))


@frappe.whitelist(allow_guest=True)
def schools(txt: str | None = None, county: str | None = None) -> list[dict]:
	filters = {"is_active": 1}
	if county:
		filters["county"] = county
	or_filters = None
	if txt:
		or_filters = {"school_name": ["like", f"%{txt}%"], "school_code": ["like", f"%{txt}%"]}
	return frappe.get_all(
		"School",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "school_name", "county", "sub_county", "education_level"],
		order_by="school_name asc",
		limit_page_length=30,
	)


def grade_sort_key(name: str) -> tuple:
	text = cstr(name).upper()
	if text.startswith("PP"):
		return (0, cint(re.sub(r"\D", "", text)), text)
	number = re.search(r"\d+", text)
	return (1, cint(number.group()) if number else 99, text)


def display_course_name(course_name: str, grade: str | None) -> str:
	"""'Grade 4 Mathematics' reads as 'Mathematics' inside the Grade 4 screen."""
	name = cstr(course_name)
	if grade and name.lower().startswith(grade.lower()):
		trimmed = name[len(grade) :].strip(" -–:()")
		return trimmed or name
	return name


def learning_areas(grade: str) -> list[dict]:
	rows = frappe.get_all(
		"Program Course",
		filters={"parent": grade, "parenttype": "Program"},
		fields=["course", "course_name", "idx"],
		order_by="idx asc",
	)
	courses = {
		c.name: c
		for c in frappe.get_all(
			"Course",
			filters={"name": ["in", [r.course for r in rows] or [""]]},
			fields=["name", "course_name", "description", "hero_image", "modified"],
		)
	}
	out = []
	for row in rows:
		course = courses.get(row.course)
		if not course:
			continue
		out.append(
			{
				"name": course.name,
				"course_name": course.course_name,
				"title": display_course_name(course.course_name, grade),
				"description": course.description,
				"image": course.hero_image,
				"order": row.idx,
				"modified": str(course.modified),
			}
		)
	return out


def strands(courses: list[str], since=None) -> list[dict]:
	if not courses:
		return []
	filters = {"subject": ["in", courses]}
	if since:
		filters["modified"] = [">", since]
	return [
		{
			"name": r.name,
			"title": r.strand_name,
			"course": r.subject,
			"description": r.description,
			"order": cint(r.order),
			"active": cint(r.active),
			"modified": str(r.modified),
		}
		for r in frappe.get_all(
			"Strand",
			filters=filters,
			fields=["name", "strand_name", "subject", "description", "order", "active", "modified"],
			limit_page_length=0,
		)
	]


def sub_strands(strand_names: list[str], since=None) -> list[dict]:
	if not strand_names:
		return []
	filters = {"strand": ["in", strand_names]}
	if since:
		filters["modified"] = [">", since]
	return [
		{
			"name": r.name,
			"title": r.name1 or r.name,
			"strand": r.strand,
			"description": r.description,
			"order": cint(r.order),
			"active": cint(r.active),
			"modified": str(r.modified),
		}
		for r in frappe.get_all(
			"Sub-strand",
			filters=filters,
			fields=["name", "name1", "strand", "description", "order", "active", "modified"],
			limit_page_length=0,
		)
	]


def outcomes(sub_strand_names: list[str], since=None) -> list[dict]:
	if not sub_strand_names:
		return []
	filters = {"sub_strand": ["in", sub_strand_names]}
	or_filters = None
	if since:
		# An outcome is resent with all its indicators when any one of them changed.
		changed = frappe.get_all(
			"Performance Indicator", filters={"modified": [">", since]}, pluck="learning_outcome", distinct=True
		)
		or_filters = {"modified": [">", since], "name": ["in", changed or [""]]}
	rows = frappe.get_all(
		"Learning Outcome",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "description", "sub_strand", "competency_area", "level", "order", "modified"],
		limit_page_length=0,
	)
	indicators = {}
	if rows:
		for pi in sorted(
			frappe.get_all(
				"Performance Indicator",
				filters={"learning_outcome": ["in", [r.name for r in rows]]},
				fields=["name", "learning_outcome", "description", "assessment_criteria", "rubric", "order"],
				limit_page_length=0,
			),
			key=lambda p: cint(p.order),
		):
			indicators.setdefault(pi.learning_outcome, []).append(
				{
					"name": pi.name,
					"description": pi.description,
					"assessment_criteria": pi.assessment_criteria,
					"rubric": pi.rubric,
					"order": cint(pi.order),
				}
			)
	return [
		{
			"name": r.name,
			"description": r.description,
			"sub_strand": r.sub_strand,
			"competency_area": r.competency_area,
			"level": r.level,
			"order": cint(r.order),
			"indicators": indicators.get(r.name, []),
			"modified": str(r.modified),
		}
		for r in rows
	]


def lesson_row(row: dict, entitled: bool) -> dict:
	out = {k: (str(v) if k == "modified" else v) for k, v in row.items()}
	out["order"] = cint(out.pop("lesson_order", 0))
	out["is_free"] = cint(out.get("is_free"))
	out["locked"] = 0
	if not entitled and not out["is_free"]:
		out["locked"] = 1
		for field in LOCKED_FIELDS:
			out[field] = None
	return out


def lessons(grade: str, entitled: bool, since=None) -> list[dict]:
	filters = {"program": grade}
	if since:
		filters["modified"] = [">", since]
	else:
		filters["published"] = 1
	rows = frappe.get_all(
		"Lesson",
		filters=filters,
		fields=LESSON_FIELDS,
		order_by="lesson_order asc, title asc",
		limit_page_length=0,
	)
	return [lesson_row(r, entitled) for r in rows]


def quizzes(quiz_names: list[str], since=None) -> tuple[list[dict], list[dict]]:
	"""Quizzes and their questions, answers included so they mark offline."""
	if not quiz_names:
		return [], []
	quiz_rows = frappe.get_all(
		"Quiz",
		filters={"name": ["in", quiz_names]},
		fields=["name", "title", "passing_score", "max_attempts", "is_time_bound", "duration", "modified"],
		limit_page_length=0,
	)
	links = frappe.get_all(
		"Quiz Question",
		filters={"parent": ["in", quiz_names], "parenttype": "Quiz"},
		fields=["parent", "question_link", "idx"],
		order_by="parent asc, idx asc",
		limit_page_length=0,
	)
	by_quiz: dict[str, list[str]] = {}
	for link in links:
		by_quiz.setdefault(link.parent, []).append(link.question_link)
	question_names = sorted({link.question_link for link in links if link.question_link})

	q_filters = {"name": ["in", question_names or [""]]}
	if since:
		q_filters["modified"] = [">", since]
	questions = frappe.get_all(
		"Question",
		filters=q_filters,
		fields=["name", "question", "question_type", "modified"],
		limit_page_length=0,
	)
	options: dict[str, list[dict]] = {}
	if questions:
		for opt in frappe.get_all(
			"Options",
			filters={"parent": ["in", [q.name for q in questions]], "parenttype": "Question"},
			fields=["name", "parent", "option", "is_correct", "idx"],
			order_by="parent asc, idx asc",
			limit_page_length=0,
		):
			options.setdefault(opt.parent, []).append(
				{"id": opt.name, "text": opt.option, "is_correct": cint(opt.is_correct)}
			)

	changed_questions = {q.name for q in questions}
	quiz_out = []
	for quiz in quiz_rows:
		if since and str(quiz.modified) <= str(since) and not changed_questions & set(by_quiz.get(quiz.name, [])):
			continue
		quiz_out.append(
			{
				"name": quiz.name,
				"title": quiz.title,
				"passing_score": quiz.passing_score,
				"max_attempts": cint(quiz.max_attempts),
				"is_time_bound": cint(quiz.is_time_bound),
				"duration": cint(quiz.duration),
				"questions": by_quiz.get(quiz.name, []),
				"modified": str(quiz.modified),
			}
		)
	question_out = [
		{
			"name": q.name,
			"question": q.question,
			"question_type": q.question_type or "Single Correct Answer",
			"options": options.get(q.name, []),
			"modified": str(q.modified),
		}
		for q in questions
	]
	return quiz_out, question_out


@frappe.whitelist()
def tree(grade: str) -> dict:
	"""The whole structure of one grade, for teachers picking where work belongs."""
	from cbc_ai_tutor.api import common

	common.current_teacher()
	if not frappe.db.exists("Program", grade):
		frappe.throw(frappe._("Grade {0} not found.").format(grade))
	areas = learning_areas(grade)
	strand_rows = strands([a["name"] for a in areas])
	sub_rows = sub_strands([s["name"] for s in strand_rows])
	outcome_rows = outcomes([s["name"] for s in sub_rows])
	return {
		"grade": grade,
		"learning_areas": areas,
		"strands": strand_rows,
		"sub_strands": sub_rows,
		"outcomes": outcome_rows,
	}
