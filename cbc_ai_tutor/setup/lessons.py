"""Lessons shipped with the app: the first topic of every core learning area, Grades 1-9, so a new
learner has something to open from their first sync, with no AI set up on the site.

Written from the KICD outcomes of each topic and kept in cbc_ai_tutor/setup/lessons/grade-N.json, one
object per lesson: learning_area, strand, sub_strand (as in the curriculum CSVs), title, minutes,
summary, body and activities (Markdown), key_vocabulary (list), reflection, and quiz (rows of a
question, four options and the index of the right one). Imported on migrate, published and free; a
topic that already has a lesson keeps it. Only re-read when the files change.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import frappe
from frappe.utils import cint, cstr, md_to_html

BUNDLED = Path(__file__).parent / "lessons"


def import_bundled_lessons() -> dict:
	files = sorted(BUNDLED.glob("*.json"))
	if not files:
		return {"created": 0}
	version = hashlib.sha1(b"".join(f.read_bytes() for f in files)).hexdigest()
	if frappe.db.get_default("cbc_bundled_lessons_version") == version:
		return {"created": 0}
	created = 0
	for file in files:
		grade = "Grade " + file.stem.split("-")[-1]
		if not frappe.db.exists("Program", grade):
			continue
		for row in json.loads(file.read_text(encoding="utf-8")):
			try:
				if add_lesson(grade, row):
					created += 1
			except Exception:
				frappe.log_error(title=f"CBC bundled lesson {grade}: {row.get('title')}")
	frappe.db.set_default("cbc_bundled_lessons_version", version)
	return {"created": created}


def _sub_strand(grade: str, row: dict) -> tuple[str, str, str] | None:
	course = f"{grade} {row['learning_area']}"
	strand = frappe.db.get_value("Strand", {"subject": course, "strand_name": cstr(row["strand"])[:140]})
	if not strand:
		return None
	sub = frappe.db.get_value("Sub-strand", {"strand": strand, "name1": cstr(row["sub_strand"])[:140]})
	return (course, strand, sub) if sub else None


def add_lesson(grade: str, row: dict) -> str | None:
	"""The lesson for its topic, unless the topic has one already. Returns the new Lesson's name."""
	from cbc_ai_tutor.ai.content import _quiz

	found = _sub_strand(grade, row)
	if not found:
		return None
	course, strand, sub = found
	if frappe.db.exists("Lesson", {"program": grade, "sub_strand": sub}):
		return None
	title = cstr(row["title"]).strip()[:140]
	outcome = frappe.get_all("Learning Outcome", filters={"sub_strand": sub}, fields=["name", "order"])
	outcome = min(outcome, key=lambda o: cint(o.order)).name if outcome else None
	lesson = frappe.get_doc(
		{
			"doctype": "Lesson",
			"title": title,
			"program": grade,
			"course": course,
			"strand": strand,
			"sub_strand": sub,
			"learning_outcome": outcome,
			"published": 1,
			"is_free": 1,
			"lesson_order": cint(frappe.db.get_value("Sub-strand", sub, "order")) * 10,
			"estimated_minutes": max(5, min(cint(row.get("minutes")) or 20, 60)),
			"summary": cstr(row.get("summary")).strip()[:500],
			"body": md_to_html(cstr(row.get("body"))),
			"key_vocabulary": ", ".join(cstr(w).strip() for w in row.get("key_vocabulary") or [] if cstr(w).strip()),
			"activities": md_to_html(cstr(row.get("activities"))),
			"reflection": cstr(row.get("reflection")).strip()[:500],
			"quiz": _quiz(f"{title} ({grade})", row.get("quiz")),
		}
	)
	lesson.insert(ignore_permissions=True)
	return lesson.name
