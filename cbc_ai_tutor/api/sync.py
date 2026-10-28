"""Offline-first sync for learners.

``pull`` returns what changed since the app's last cursor: the learner's grade
content (lessons locked when the family has no access), and the learner's own
records. ``push`` takes a batch of events the app queued while offline. Each event
carries a client-generated id and is applied exactly once, however many times a
flaky connection makes the app resend it. Quiz attempts are re-marked on the
server; the score the app showed offline is never trusted.
"""

from __future__ import annotations

import base64
import json
import os

import frappe
from frappe import _
from frappe.utils import (
	cint,
	cstr,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	nowdate,
	time_diff_in_seconds,
)

from cbc_ai_tutor.api import common, curriculum

SYNCED_TYPES = ("Lesson", "Strand", "Sub-strand", "Learning Outcome", "Quiz", "Question")
MAX_EVENTS = 200
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
UPLOAD_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf", ".doc", ".docx", ".txt", ".mp3", ".m4a"}
MAX_TIME_PER_EVENT = 4 * 60 * 60


def _learner_scope(student: str) -> frappe._dict:
	row = frappe.db.get_value(
		"Student", student, ["name", "student_name", "custom_grade", "custom_school"], as_dict=True
	)
	if not row.custom_grade:
		frappe.throw(_("This learner has no grade yet. A parent can set it from their app."))
	return row


@frappe.whitelist()
def pull(
	since: str | None = None,
	grade: str | None = None,
	entitled: int | str | None = None,
) -> dict:
	"""Changes since ``since``. Send back the ``cursor`` from the last pull.

	``grade`` and ``entitled`` are what the app currently holds. When either no
	longer matches, everything is resent, so a learner moved up a grade or a family
	that just paid gets the right content without the app having to know why.
	"""
	student = common.current_learner()
	scope = _learner_scope(student)
	ent = common.entitlement_for_student(student)
	server_time = now_datetime()

	full = (
		not since
		or (grade and grade != scope.custom_grade)
		or (entitled not in (None, "") and bool(cint(entitled)) != bool(ent.active))
	)
	cutoff = None if full else get_datetime(since)

	areas = curriculum.learning_areas(scope.custom_grade)
	course_names = [a["name"] for a in areas]
	all_strands = frappe.get_all("Strand", filters={"subject": ["in", course_names or [""]]}, pluck="name")
	all_subs = frappe.get_all(
		"Sub-strand", filters={"strand": ["in", all_strands or [""]]}, pluck="name"
	)

	strand_rows = curriculum.strands(course_names, cutoff)
	sub_rows = curriculum.sub_strands(all_strands, cutoff)
	outcome_rows = curriculum.outcomes(all_subs, cutoff)
	lesson_rows = curriculum.lessons(scope.custom_grade, ent.active, cutoff)

	deleted: dict[str, list[str]] = {}
	visible_lessons = []
	for row in lesson_rows:
		if not cint(row.get("published")):
			deleted.setdefault("Lesson", []).append(row["name"])
		else:
			visible_lessons.append(row)
	for row in strand_rows + sub_rows:
		if not row["active"]:
			deleted.setdefault("Strand" if "course" in row else "Sub-strand", []).append(row["name"])

	open_quizzes = frappe.get_all(
		"Lesson",
		filters={"program": scope.custom_grade, "published": 1, "quiz": ["is", "set"]},
		fields=["quiz", "is_free"],
		limit_page_length=0,
	)
	quiz_names = sorted({q.quiz for q in open_quizzes if ent.active or cint(q.is_free)})
	relinked = sorted({row["quiz"] for row in visible_lessons if row.get("quiz")} & set(quiz_names))
	quiz_rows, question_rows = curriculum.quizzes(relinked, None) if cutoff else ([], [])
	rest_quizzes, rest_questions = curriculum.quizzes(
		[q for q in quiz_names if q not in relinked] if cutoff else quiz_names, cutoff
	)
	seen_questions = {q["name"] for q in question_rows}
	quiz_rows += rest_quizzes
	question_rows += [q for q in rest_questions if q["name"] not in seen_questions]

	if cutoff:
		for row in frappe.get_all(
			"Deleted Document",
			filters={"deleted_doctype": ["in", SYNCED_TYPES], "creation": [">", cutoff]},
			fields=["deleted_doctype", "deleted_name"],
			limit_page_length=0,
		):
			deleted.setdefault(row.deleted_doctype, []).append(row.deleted_name)

	return {
		"cursor": str(server_time),
		"full": 1 if full else 0,
		"learner": {
			"student": student,
			"name": scope.student_name,
			"grade": scope.custom_grade,
			"school": scope.custom_school,
		},
		"entitlement": {
			"active": 1 if ent.active else 0,
			"status": ent.status,
			"until": str(ent.until) if ent.until else None,
			"ai_messages_per_day": ent.ai_messages_per_day,
		},
		"learning_areas": areas,
		"strands": strand_rows,
		"sub_strands": sub_rows,
		"outcomes": outcome_rows,
		"lessons": visible_lessons,
		"quizzes": quiz_rows,
		"questions": question_rows,
		"deleted": deleted,
		"mine": _own_records(student, scope, cutoff),
	}


def _own_records(student: str, scope: frappe._dict, cutoff) -> dict:
	since = {"modified": [">", cutoff]} if cutoff else {}

	progress = frappe.get_all(
		"Lesson Progress",
		filters={"student": student, **since},
		fields=["lesson", "status", "progress", "time_spent", "last_opened", "completed_on", "modified"],
		limit_page_length=0,
	)
	attempts = frappe.get_all(
		"Quiz Submission",
		filters={"student": student, **since},
		fields=[
			"name",
			"client_uuid",
			"quiz",
			"lesson",
			"attempt_number",
			"score",
			"status",
			"time_completed",
			"modified",
		],
		order_by="modified desc",
		limit_page_length=500,
	)
	assignments = visible_assignments(scope, cutoff)
	submissions = frappe.get_all(
		"Assignment Submission",
		filters={"student": student, **since},
		fields=[
			"name",
			"client_uuid",
			"assignment",
			"status",
			"grade_given",
			"remarks",
			"submission_date",
			"answer_text",
			"attachment",
			"modified",
		],
		limit_page_length=0,
	)
	competencies = frappe.get_all(
		"Student Competency Progress",
		filters={"student": student, **since},
		fields=["name", "learning_outcome", "performance_indicator", "status", "comments", "date", "modified"],
		limit_page_length=0,
	)
	return {
		"lesson_progress": _stringify(progress),
		"quiz_attempts": _stringify(attempts),
		"assignments": _stringify(assignments),
		"submissions": _stringify(submissions),
		"competencies": _stringify(competencies),
		"ai_quota": ai_quota(student),
	}


def _stringify(rows: list[dict]) -> list[dict]:
	out = []
	for row in rows:
		out.append({k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()})
	return out


def visible_assignments(scope: frappe._dict, cutoff=None) -> list[dict]:
	"""Published work set for this learner's grade by a teacher at their school."""
	if not scope.custom_school:
		return []
	teachers = frappe.get_all("Instructor", filters={"custom_school": scope.custom_school}, pluck="name")
	if not teachers:
		return []
	filters = {
		"grade": scope.custom_grade,
		"instructor": ["in", teachers],
		"status": ["in", ["Published", "Closed"]],
		"is_active": 1,
	}
	if cutoff:
		filters["modified"] = [">", cutoff]
	return frappe.get_all(
		"Assignment",
		filters=filters,
		fields=[
			"name",
			"title",
			"assignment_type",
			"description",
			"due_date",
			"attachment",
			"strand",
			"sub_strand",
			"learning_outcome",
			"competency_type",
			"status",
			"published_on",
			"modified",
		],
		order_by="due_date asc",
		limit_page_length=0,
	)


def ai_quota(student: str) -> dict:
	ent = common.entitlement_for_student(student)
	limit = cint(ent.ai_messages_per_day)
	used = frappe.db.count(
		"AI Tutor Interaction",
		{"student": student, "date": [">=", nowdate() + " 00:00:00"]},
	)
	return {
		"enabled": 1 if cint(common.setting("ai_enabled", 1)) and ent.active else 0,
		"limit": limit,
		"used": used,
		"remaining": None if limit == 0 else max(limit - used, 0),
	}


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def push(events) -> dict:
	student = common.current_learner()
	scope = _learner_scope(student)
	if isinstance(events, str):
		events = json.loads(events or "[]")
	if not isinstance(events, list):
		frappe.throw(_("events must be a list."))
	if len(events) > MAX_EVENTS:
		frappe.throw(_("Send at most {0} events at a time.").format(MAX_EVENTS))

	results = []
	for event in events:
		uuid = cstr((event or {}).get("uuid")).strip()
		kind = cstr((event or {}).get("type")).strip()
		if not uuid or len(uuid) > 64:
			results.append({"uuid": uuid, "ok": 0, "error": "missing_uuid"})
			continue

		done = frappe.db.get_value("CBC Sync Receipt", uuid, ["student", "result"], as_dict=True)
		if done:
			if done.student != student:
				results.append({"uuid": uuid, "ok": 0, "error": "uuid_in_use"})
			else:
				results.append({"uuid": uuid, "ok": 1, "duplicate": 1, "result": json.loads(done.result or "{}")})
			continue

		handler = HANDLERS.get(kind)
		if not handler:
			results.append({"uuid": uuid, "ok": 0, "error": "unknown_type"})
			continue

		frappe.db.savepoint("cbc_sync_event")
		try:
			result = handler(student, scope, event.get("payload") or {}, event) or {}
			frappe.get_doc(
				{
					"doctype": "CBC Sync Receipt",
					"client_uuid": uuid,
					"student": student,
					"event_type": kind,
					"reference_doctype": result.get("doctype"),
					"reference_name": result.get("name"),
					"result": json.dumps(result, default=str),
				}
			).insert(ignore_permissions=True)
			results.append({"uuid": uuid, "ok": 1, "result": result})
		except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
			frappe.db.rollback(save_point="cbc_sync_event")
			frappe.clear_messages()
			results.append({"uuid": uuid, "ok": 0, "error": getattr(e, "cbc_code", "rejected"), "message": cstr(e)})
		except Exception:
			frappe.db.rollback(save_point="cbc_sync_event")
			frappe.clear_messages()
			frappe.log_error(title=f"CBC sync event {kind} failed", message=frappe.get_traceback())
			results.append({"uuid": uuid, "ok": 0, "error": "server_error", "retry": 1})

	return {"results": results, "server_time": str(now_datetime())}


class SyncRejected(frappe.ValidationError):
	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.cbc_code = code


def _lesson_for(student: str, scope: frappe._dict, lesson: str) -> frappe._dict:
	row = frappe.db.get_value(
		"Lesson", lesson, ["name", "program", "published", "is_free", "quiz"], as_dict=True
	)
	if not row or row.program != scope.custom_grade or not row.published:
		raise SyncRejected("lesson_unavailable", _("That lesson is not part of your grade."))
	if not row.is_free and not common.entitlement_for_student(student).active:
		raise SyncRejected("subscription_required", _("This lesson needs an active subscription."))
	return row


def _when(value, fallback=None):
	try:
		when = get_datetime(value) if value else None
	except Exception:
		when = None
	now = now_datetime()
	if not when or when > now:
		return fallback or now
	return when


def handle_lesson_progress(student, scope, payload, event):
	lesson = _lesson_for(student, scope, cstr(payload.get("lesson")))
	at = _when(payload.get("at") or event.get("at"))
	delta = max(0, min(cint(payload.get("time_spent_delta")), MAX_TIME_PER_EVENT))
	progress = max(0.0, min(flt(payload.get("progress")), 100.0))
	completed = cint(payload.get("completed")) or progress >= 100

	name = frappe.db.get_value("Lesson Progress", {"student": student, "lesson": lesson.name}, "name")
	if name:
		doc = frappe.get_doc("Lesson Progress", name)
	else:
		doc = frappe.get_doc(
			{"doctype": "Lesson Progress", "student": student, "lesson": lesson.name, "first_opened": at}
		)
	doc.progress = max(flt(doc.progress), 100.0 if completed else progress)
	doc.time_spent = cint(doc.time_spent) + delta
	if not doc.last_opened or get_datetime(doc.last_opened) < at:
		doc.last_opened = at
	if completed and doc.status != "Completed":
		doc.status = "Completed"
		doc.completed_on = at
	doc.save(ignore_permissions=True)
	return {"doctype": "Lesson Progress", "name": doc.name, "status": doc.status, "progress": doc.progress}


def grade_answers(quiz: str, answers: list) -> tuple[float, list[dict]]:
	"""Score a quiz from option ids (or option text, for older app builds)."""
	question_names = frappe.get_all(
		"Quiz Question",
		filters={"parent": quiz, "parenttype": "Quiz"},
		pluck="question_link",
		order_by="idx asc",
	)
	if not question_names:
		raise SyncRejected("quiz_empty", _("This quiz has no questions."))
	options = frappe.get_all(
		"Options",
		filters={"parent": ["in", question_names], "parenttype": "Question"},
		fields=["name", "parent", "option", "is_correct"],
		limit_page_length=0,
	)
	by_question: dict[str, list] = {}
	for opt in options:
		by_question.setdefault(opt.parent, []).append(opt)

	given = {}
	for answer in answers or []:
		question = cstr(answer.get("question"))
		selected = answer.get("selected") or []
		if isinstance(selected, str):
			selected = [selected]
		given[question] = [cstr(s) for s in selected][:10]

	rows, correct_count = [], 0
	for question in question_names:
		opts = by_question.get(question, [])
		correct_ids = {o.name for o in opts if cint(o.is_correct)}
		chosen_ids = set()
		labels = []
		for value in given.get(question, []):
			match = next((o for o in opts if o.name == value), None) or next(
				(o for o in opts if cstr(o.option).strip() == value.strip()), None
			)
			if match:
				chosen_ids.add(match.name)
				labels.append(cstr(match.option))
		is_correct = bool(correct_ids) and chosen_ids == correct_ids
		correct_count += 1 if is_correct else 0
		rows.append(
			{
				"question": question,
				"selected": ", ".join(labels)[:140],
				"is_correct": 1 if is_correct else 0,
			}
		)
	score = round(correct_count * 100.0 / len(question_names), 2)
	return score, rows


def handle_quiz_attempt(student, scope, payload, event):
	uuid = cstr(event.get("uuid"))
	existing = frappe.db.get_value("Quiz Submission", {"client_uuid": uuid}, ["name", "score", "status"], as_dict=True)
	if existing:
		return {"doctype": "Quiz Submission", "name": existing.name, "score": existing.score, "status": existing.status}

	quiz = cstr(payload.get("quiz"))
	lesson_name = cstr(payload.get("lesson"))
	if lesson_name:
		lesson = _lesson_for(student, scope, lesson_name)
		if lesson.quiz != quiz:
			raise SyncRejected("quiz_mismatch", _("That quiz does not belong to this lesson."))
	else:
		lesson_name = frappe.db.get_value("Lesson", {"quiz": quiz, "program": scope.custom_grade, "published": 1}, "name")
		if not lesson_name:
			raise SyncRejected("quiz_unavailable", _("That quiz is not part of your grade."))
		_lesson_for(student, scope, lesson_name)

	conf = frappe.db.get_value("Quiz", quiz, ["passing_score", "max_attempts"], as_dict=True)
	attempts = frappe.db.count("Quiz Submission", {"quiz": quiz, "student": student})
	if cint(conf.max_attempts) and attempts >= cint(conf.max_attempts):
		raise SyncRejected("max_attempts", _("You have used all {0} attempts on this quiz.").format(conf.max_attempts))

	score, rows = grade_answers(quiz, payload.get("answers") or [])
	completed = _when(payload.get("completed_at") or event.get("at"))
	started = _when(payload.get("started_at"), completed)
	if started > completed:
		started = completed

	doc = frappe.get_doc(
		{
			"doctype": "Quiz Submission",
			"quiz": quiz,
			"student": student,
			"lesson": lesson_name,
			"attempt_number": attempts + 1,
			"score": score,
			"status": "Completed" if score >= flt(conf.passing_score) else "Failed",
			"time_started": started,
			"time_completed": completed,
			"time_taken": max(0, cint(time_diff_in_seconds(completed, started))),
			"answers": rows,
			"client_uuid": uuid,
		}
	)
	doc.insert(ignore_permissions=True)
	return {
		"doctype": "Quiz Submission",
		"name": doc.name,
		"score": score,
		"status": doc.status,
		"attempt_number": doc.attempt_number,
		"answers": rows,
	}


def handle_assignment_submission(student, scope, payload, event):
	uuid = cstr(event.get("uuid"))
	assignment = cstr(payload.get("assignment"))
	visible = {a.name: a for a in visible_assignments(scope)}
	work = visible.get(assignment)
	if not work:
		raise SyncRejected("assignment_unavailable", _("That assignment is not set for you."))
	if work.status == "Closed":
		raise SyncRejected("assignment_closed", _("This assignment has closed."))

	text = cstr(payload.get("answer_text")).strip()
	attachment = cstr(payload.get("attachment")).strip() or None
	if attachment and not _owns_file(student, attachment):
		raise SyncRejected("bad_attachment", _("Upload the file again, then submit."))
	if not text and not attachment:
		raise SyncRejected("empty", _("Write an answer or attach your work."))

	submitted_at = _when(payload.get("submitted_at") or event.get("at"))
	late = bool(work.due_date and getdate(submitted_at) > getdate(work.due_date))

	name = frappe.db.get_value("Assignment Submission", {"assignment": assignment, "student": student}, "name")
	if name:
		doc = frappe.get_doc("Assignment Submission", name)
		if doc.status == "Reviewed":
			raise SyncRejected("already_reviewed", _("Your teacher has already reviewed this work."))
	else:
		doc = frappe.get_doc({"doctype": "Assignment Submission", "assignment": assignment, "student": student})
	doc.answer_text = frappe.utils.escape_html(text).replace("\n", "<br>") if text else None
	doc.attachment = attachment
	doc.submission_date = submitted_at
	doc.status = "Late" if late else "Submitted"
	doc.client_uuid = uuid
	doc.save(ignore_permissions=True)
	if attachment:
		_attach_file_to(attachment, "Assignment Submission", doc.name)
	return {"doctype": "Assignment Submission", "name": doc.name, "status": doc.status}


def handle_practice_answers(student, scope, payload, event):
	from cbc_ai_tutor.api import tutor

	return tutor.grade_practice_for(student, cstr(payload.get("practice")), payload.get("answers") or [])


def handle_ai_feedback(student, scope, payload, event):
	name = cstr(payload.get("interaction"))
	if frappe.db.get_value("AI Tutor Interaction", name, "student") != student:
		raise SyncRejected("not_found", _("That tutor message is not yours."))
	helpful = "Helpful" if cint(payload.get("helpful")) else "Not helpful"
	comment = frappe.utils.escape_html(cstr(payload.get("comment"))[:1000])
	frappe.db.set_value("AI Tutor Interaction", name, "feedback", f"{helpful}. {comment}".strip())
	return {"doctype": "AI Tutor Interaction", "name": name}


HANDLERS = {
	"lesson_progress": handle_lesson_progress,
	"quiz_attempt": handle_quiz_attempt,
	"assignment_submission": handle_assignment_submission,
	"practice_answers": handle_practice_answers,
	"ai_feedback": handle_ai_feedback,
}


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def _owns_file(student: str, file_url: str) -> bool:
	return bool(
		frappe.db.exists(
			"File",
			{
				"file_url": file_url,
				"attached_to_doctype": ["in", ["Student", "Assignment Submission"]],
				"attached_to_name": ["in", [student, *frappe.get_all("Assignment Submission", {"student": student}, pluck="name")]],
			},
		)
	)


def _attach_file_to(file_url: str, doctype: str, name: str):
	file_name = frappe.db.get_value("File", {"file_url": file_url, "attached_to_doctype": "Student"}, "name")
	if file_name:
		frappe.db.set_value("File", file_name, {"attached_to_doctype": doctype, "attached_to_name": name})


@frappe.whitelist(methods=["POST"])
def upload(filename: str, content: str) -> dict:
	"""A learner's photo or document, base64 encoded. Stored private."""
	student = common.current_learner()
	return save_upload(filename, content, "Student", student)


def save_upload(filename: str, content: str, doctype: str, name: str) -> dict:
	filename = os.path.basename(cstr(filename)).strip()
	ext = os.path.splitext(filename)[1].lower()
	if not filename or ext not in UPLOAD_TYPES:
		frappe.throw(_("Upload a photo, PDF, Word document or voice note."))
	try:
		data = base64.b64decode(content or "", validate=True)
	except Exception:
		frappe.throw(_("The file could not be read. Try again."))
	if not data:
		frappe.throw(_("The file is empty."))
	if len(data) > MAX_UPLOAD_BYTES:
		frappe.throw(_("Files can be up to {0} MB.").format(MAX_UPLOAD_BYTES // (1024 * 1024)))

	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"content": data,
			"is_private": 1,
			"attached_to_doctype": doctype,
			"attached_to_name": name,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert()
	return {"file_url": doc.file_url, "file_name": doc.file_name, "size": len(data)}


@frappe.whitelist()
def file(file_url: str) -> dict:
	"""Download a file the learner is allowed to see: their own work, or an assignment's sheet."""
	student = common.current_learner()
	scope = _learner_scope(student)
	allowed = _owns_file(student, file_url) or any(
		a.attachment == file_url for a in visible_assignments(scope)
	)
	if not allowed:
		raise frappe.PermissionError(_("You can't open that file."))
	return file_payload(file_url)


def file_payload(file_url: str) -> dict:
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		raise frappe.DoesNotExistError(_("File not found."))
	doc = frappe.get_doc("File", name)
	content = doc.get_content()
	if isinstance(content, str):
		content = content.encode()
	return {"file_name": doc.file_name, "content": base64.b64encode(content).decode()}
