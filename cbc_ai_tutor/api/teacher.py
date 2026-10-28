"""The teacher experience: learners at their school, assignments, reviews, CBC records.

A teacher sees learners whose Student record names the teacher's school. Their
own assignments are the ones linked to their Instructor record.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, escape_html, flt, getdate, now_datetime, nowdate, strip_html

from cbc_ai_tutor.api import common, progress, sync

ASSIGNMENT_TYPES = ("Homework", "Assignment", "Project", "Quiz")
COMPETENCY_TYPES = ("Knowledge", "Skills", "Values & Attitudes")
COMPETENCY_LEVELS = ("Emerging", "Proficient", "Advanced")
ASSESSMENT_TYPES = ("Quiz", "Project", "Observation", "Test", "Assignment")
ASSIGNMENT_FIELDS = [
	"name",
	"title",
	"assignment_type",
	"description",
	"due_date",
	"attachment",
	"grade",
	"strand",
	"sub_strand",
	"learning_outcome",
	"performance_indicator",
	"competency_type",
	"status",
	"is_active",
	"published_on",
	"modified",
]


def _school_students(teacher, grade: str | None = None) -> list[str]:
	if not teacher.school:
		return []
	filters = {"custom_school": teacher.school, "enabled": 1}
	if grade:
		filters["custom_grade"] = grade
	return frappe.get_all("Student", filters=filters, pluck="name", limit_page_length=0)


def _html(text: str | None) -> str | None:
	text = cstr(text).strip()
	return escape_html(text).replace("\n", "<br>") if text else None


@frappe.whitelist()
def dashboard() -> dict:
	teacher = common.current_teacher()
	students = _school_students(teacher)
	grades = frappe.db.sql(
		"""select custom_grade as grade, count(*) as learners from `tabStudent`
		where custom_school=%s and enabled=1 and ifnull(custom_grade, '') != ''
		group by custom_grade""",
		teacher.school or "",
		as_dict=True,
	)
	from cbc_ai_tutor.api.curriculum import grade_sort_key

	mine = frappe.get_all("Assignment", filters={"instructor": teacher.name}, pluck="name", limit_page_length=0)
	return {
		"instructor": teacher.name,
		"instructor_name": frappe.db.get_value("Instructor", teacher.name, "instructor_name"),
		"school": teacher.school,
		"learners": len(students),
		"grades": sorted(grades, key=lambda g: grade_sort_key(g.grade)),
		"open_assignments": frappe.db.count(
			"Assignment", {"instructor": teacher.name, "status": "Published", "is_active": 1}
		),
		"to_review": frappe.db.count(
			"Assignment Submission",
			{"assignment": ["in", mine or [""]], "status": ["in", ["Submitted", "Late"]]},
		),
		"unanswered_feedback": frappe.db.count(
			"Parental Feedback",
			{"student": ["in", students or [""]], "response": ["is", "not set"]},
		),
	}


# ---------------------------------------------------------------------------
# Learners
# ---------------------------------------------------------------------------


@frappe.whitelist()
def students(grade: str | None = None, txt: str | None = None, limit: int = 100, start: int = 0) -> list[dict]:
	teacher = common.current_teacher()
	if not teacher.school:
		return []
	filters = {"custom_school": teacher.school, "enabled": 1}
	if grade:
		filters["custom_grade"] = grade
	or_filters = {"student_name": ["like", f"%{txt}%"], "custom_learner_code": ["like", f"%{txt}%"]} if txt else None
	rows = frappe.get_all(
		"Student",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "student_name", "custom_grade", "custom_learner_code", "image", "gender"],
		order_by="student_name asc",
		limit_start=cint(start),
		limit_page_length=common.paginate(limit, 100, 500),
	)
	out = []
	for row in rows:
		item = {
			"student": row.name,
			"name": row.student_name,
			"grade": row.custom_grade,
			"learner_code": row.custom_learner_code,
			"image": row.image,
			"gender": row.gender,
		}
		item.update(progress.summary(row.name))
		out.append(item)
	return out


@frappe.whitelist()
def student_progress(student: str) -> dict:
	common.assert_teacher_of(student)
	return progress.report(student)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


def _own_assignment(name: str):
	teacher = common.current_teacher()
	doc = frappe.get_doc("Assignment", name)
	if doc.instructor != teacher.name:
		raise frappe.PermissionError(_("That assignment belongs to another teacher."))
	return doc, teacher


@frappe.whitelist()
def assignments(status: str | None = None, grade: str | None = None, limit: int = 100) -> list[dict]:
	teacher = common.current_teacher()
	filters = {"instructor": teacher.name}
	if status:
		filters["status"] = status
	if grade:
		filters["grade"] = grade
	rows = frappe.get_all(
		"Assignment",
		filters=filters,
		fields=ASSIGNMENT_FIELDS,
		order_by="modified desc",
		limit_page_length=common.paginate(limit, 100, 500),
	)
	counts = {
		r.assignment: r
		for r in frappe.db.sql(
			"""select assignment, count(*) as submitted,
				sum(status in ('Submitted', 'Late')) as to_review
			from `tabAssignment Submission` where assignment in %(names)s group by assignment""",
			{"names": [r.name for r in rows] or [""]},
			as_dict=True,
		)
	}
	for row in rows:
		c = counts.get(row.name)
		row["submitted"] = cint(c.submitted) if c else 0
		row["to_review"] = cint(c.to_review) if c else 0
		row["description"] = row.description or ""
	return sync._stringify(rows)


@frappe.whitelist()
def assignment(name: str) -> dict:
	doc, _teacher = _own_assignment(name)
	return sync._stringify([{f: doc.get(f) for f in ASSIGNMENT_FIELDS}])[0]


def _check_curriculum_links(grade, strand, sub_strand, learning_outcome, performance_indicator):
	if not frappe.db.exists("Program", grade):
		frappe.throw(_("Pick a grade."))
	if strand:
		course = frappe.db.get_value("Strand", strand, "subject")
		if course and not frappe.db.exists("Program Course", {"parent": grade, "course": course}):
			frappe.throw(_("That strand is not taught in {0}.").format(grade))
	if sub_strand and strand and frappe.db.get_value("Sub-strand", sub_strand, "strand") != strand:
		frappe.throw(_("That sub-strand is not part of the strand."))
	if learning_outcome and sub_strand and frappe.db.get_value("Learning Outcome", learning_outcome, "sub_strand") != sub_strand:
		frappe.throw(_("That learning outcome is not part of the sub-strand."))
	if performance_indicator and learning_outcome and (
		frappe.db.get_value("Performance Indicator", performance_indicator, "learning_outcome") != learning_outcome
	):
		frappe.throw(_("That performance indicator is not part of the learning outcome."))


@frappe.whitelist(methods=["POST"])
def save_assignment(
	title: str,
	grade: str,
	assignment_type: str = "Assignment",
	description: str | None = None,
	due_date: str | None = None,
	strand: str | None = None,
	sub_strand: str | None = None,
	learning_outcome: str | None = None,
	performance_indicator: str | None = None,
	competency_type: str | None = None,
	attachment: str | None = None,
	name: str | None = None,
) -> dict:
	"""Create a draft, or edit one of your own assignments."""
	if name:
		doc, teacher = _own_assignment(name)
	else:
		teacher = common.current_teacher()
		doc = frappe.get_doc({"doctype": "Assignment", "instructor": teacher.name, "status": "Draft", "is_active": 1})

	title = cstr(title).strip()
	if len(title) < 3:
		frappe.throw(_("Give the assignment a title."))
	if assignment_type not in ASSIGNMENT_TYPES:
		frappe.throw(_("Pick the kind of work."))
	if competency_type and competency_type not in COMPETENCY_TYPES:
		frappe.throw(_("Pick a competency type from the list."))
	if due_date and getdate(due_date) < getdate(nowdate()) and doc.status == "Draft":
		frappe.throw(_("The due date has already passed."))
	_check_curriculum_links(grade, strand, sub_strand, learning_outcome, performance_indicator)
	if sub_strand and not strand:
		strand = frappe.db.get_value("Sub-strand", sub_strand, "strand")
	if attachment and not frappe.db.exists(
		"File", {"file_url": attachment, "attached_to_doctype": ["in", ["Instructor", "Assignment"]], "attached_to_name": ["in", [teacher.name, doc.name or ""]]}
	):
		frappe.throw(_("Upload the file again, then save."))

	doc.update(
		{
			"title": title[:140],
			"assignment_type": assignment_type,
			"description": cstr(description).strip() or None,
			"due_date": due_date or None,
			"grade": grade,
			"strand": strand or None,
			"sub_strand": sub_strand or None,
			"learning_outcome": learning_outcome or None,
			"performance_indicator": performance_indicator or None,
			"competency_type": competency_type or None,
			"attachment": attachment or None,
		}
	)
	doc.flags.ignore_permissions = True
	doc.save()
	if attachment:
		file_name = frappe.db.get_value("File", {"file_url": attachment, "attached_to_doctype": "Instructor"}, "name")
		if file_name:
			frappe.db.set_value("File", file_name, {"attached_to_doctype": "Assignment", "attached_to_name": doc.name})
	return assignment(doc.name)


@frappe.whitelist(methods=["POST"])
def set_assignment_status(name: str, status: str) -> dict:
	"""Publish (learners see it on their next sync), close, or reopen."""
	doc, _teacher = _own_assignment(name)
	if status not in ("Published", "Closed", "Draft"):
		frappe.throw(_("Unknown status."))
	if status == "Draft" and frappe.db.exists("Assignment Submission", {"assignment": name}):
		frappe.throw(_("Learners have already handed in work, so it can only be closed."))
	doc.status = status
	if status == "Published" and not doc.published_on:
		doc.published_on = now_datetime()
	doc.flags.ignore_permissions = True
	doc.save()
	return assignment(name)


@frappe.whitelist(methods=["POST"])
def delete_assignment(name: str) -> dict:
	doc, _teacher = _own_assignment(name)
	if frappe.db.exists("Assignment Submission", {"assignment": name}):
		frappe.throw(_("Learners have handed in work. Close the assignment instead."))
	frappe.delete_doc("Assignment", doc.name, ignore_permissions=True)
	return {"deleted": name}


@frappe.whitelist(methods=["POST"])
def upload(filename: str, content: str) -> dict:
	"""An assignment sheet. Attach it with ``save_assignment(attachment=file_url)``."""
	teacher = common.current_teacher()
	return sync.save_upload(filename, content, "Instructor", teacher.name)


@frappe.whitelist()
def file(file_url: str) -> dict:
	"""A file handed in by a learner at the teacher's school, or the teacher's own sheet."""
	teacher = common.current_teacher()
	row = frappe.db.get_value("File", {"file_url": file_url}, ["attached_to_doctype", "attached_to_name"], as_dict=True)
	allowed = False
	if row and row.attached_to_doctype == "Instructor":
		allowed = row.attached_to_name == teacher.name
	elif row and row.attached_to_doctype == "Assignment":
		allowed = frappe.db.get_value("Assignment", row.attached_to_name, "instructor") == teacher.name
	elif row and teacher.school:
		student = None
		if row.attached_to_doctype == "Assignment Submission":
			student = frappe.db.get_value("Assignment Submission", row.attached_to_name, "student")
		elif row.attached_to_doctype == "Student":
			student = row.attached_to_name
		allowed = bool(student) and frappe.db.get_value("Student", student, "custom_school") == teacher.school
	if not allowed:
		raise frappe.PermissionError(_("You can't open that file."))
	return sync.file_payload(file_url)


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


@frappe.whitelist()
def submissions(assignment: str) -> dict:
	"""Every learner the work was set for, with what they handed in."""
	doc, teacher = _own_assignment(assignment)
	learners = frappe.get_all(
		"Student",
		filters={"custom_school": teacher.school or "", "custom_grade": doc.grade, "enabled": 1},
		fields=["name", "student_name"],
		order_by="student_name asc",
		limit_page_length=0,
	)
	handed_in = {
		s.student: s
		for s in frappe.get_all(
			"Assignment Submission",
			filters={"assignment": assignment},
			fields=["name", "student", "status", "submission_date", "answer_text", "attachment", "grade_given", "remarks", "reviewed_on"],
			limit_page_length=0,
		)
	}
	rows = []
	for learner in learners:
		s = handed_in.pop(learner.name, None)
		rows.append(_submission_row(learner.name, learner.student_name, s))
	for student, s in handed_in.items():
		rows.append(_submission_row(student, frappe.db.get_value("Student", student, "student_name"), s))
	return {"assignment": assignment, "title": doc.title, "due_date": str(doc.due_date or ""), "learners": rows}


def _submission_row(student, student_name, s) -> dict:
	row = {"student": student, "student_name": student_name, "status": "Not submitted"}
	if s:
		row.update(
			{
				"submission": s.name,
				"status": s.status,
				"submitted_on": str(s.submission_date or ""),
				"answer_text": s.answer_text,
				"attachment": s.attachment,
				"grade_given": s.grade_given,
				"remarks": s.remarks,
				"reviewed_on": str(s.reviewed_on or ""),
			}
		)
	return row


@frappe.whitelist(methods=["POST"])
def review_submission(name: str, grade_given: str | None = None, remarks: str | None = None, status: str = "Reviewed") -> dict:
	"""Mark the work. 'Returned' sends it back for the learner to redo."""
	sub = frappe.get_doc("Assignment Submission", name)
	_own_assignment(sub.assignment)
	if status not in ("Reviewed", "Returned"):
		frappe.throw(_("Mark the work as reviewed or return it."))
	sub.grade_given = cstr(grade_given).strip()[:140] or None
	sub.remarks = cstr(remarks).strip()[:2000] or None
	sub.status = status
	sub.reviewed_by = frappe.session.user
	sub.reviewed_on = now_datetime()
	sub.flags.ignore_permissions = True
	sub.save()
	return _submission_row(sub.student, frappe.db.get_value("Student", sub.student, "student_name"), sub)


# ---------------------------------------------------------------------------
# CBC records
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def record_competency(
	student: str,
	learning_outcome: str,
	status: str,
	performance_indicator: str | None = None,
	comments: str | None = None,
	evidence: str | None = None,
	date: str | None = None,
) -> dict:
	"""Where the learner is on an outcome: Emerging, Proficient or Advanced."""
	teacher = common.assert_teacher_of(student)
	if status not in COMPETENCY_LEVELS:
		frappe.throw(_("Pick Emerging, Proficient or Advanced."))
	if not frappe.db.exists("Learning Outcome", learning_outcome):
		frappe.throw(_("Pick a learning outcome."))
	if performance_indicator and frappe.db.get_value("Performance Indicator", performance_indicator, "learning_outcome") != learning_outcome:
		frappe.throw(_("That performance indicator is not part of the learning outcome."))
	if evidence and not frappe.db.exists("File", {"file_url": evidence, "attached_to_doctype": "Instructor", "attached_to_name": teacher.name}):
		frappe.throw(_("Upload the evidence again, then save."))
	doc = frappe.get_doc(
		{
			"doctype": "Student Competency Progress",
			"student": student,
			"learning_outcome": learning_outcome,
			"performance_indicator": performance_indicator or None,
			"status": status,
			"comments": cstr(comments).strip()[:1000] or None,
			"evidence": evidence or None,
			"date": date or nowdate(),
			"teacher": teacher.user,
		}
	).insert(ignore_permissions=True)
	return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def record_assessment(
	student: str,
	subject: str,
	assessment_type: str,
	score: float,
	max_score: float,
	comments: str | None = None,
	strand: str | None = None,
	sub_strand: str | None = None,
	learning_outcome: str | None = None,
	date: str | None = None,
) -> dict:
	teacher = common.assert_teacher_of(student)
	if assessment_type not in ASSESSMENT_TYPES:
		frappe.throw(_("Pick the kind of assessment."))
	if not frappe.db.exists("Course", subject):
		frappe.throw(_("Pick a learning area."))
	score, max_score = flt(score), flt(max_score)
	if max_score <= 0 or score < 0 or score > max_score:
		frappe.throw(_("The score must be between 0 and the maximum."))
	doc = frappe.get_doc(
		{
			"doctype": "Continuous Assessment",
			"student": student,
			"subject": subject,
			"strand": strand or None,
			"sub_strand": sub_strand or None,
			"learning_outcome": learning_outcome or None,
			"date": date or nowdate(),
			"assessment_type": assessment_type,
			"score": score,
			"max_score": max_score,
			"comments": _html(comments),
			"teacher": teacher.user,
		}
	).insert(ignore_permissions=True)
	return {"name": doc.name}


# ---------------------------------------------------------------------------
# Messages from parents
# ---------------------------------------------------------------------------


@frappe.whitelist()
def feedback(unanswered: int | str = 0, limit: int = 50) -> list[dict]:
	teacher = common.current_teacher()
	students = _school_students(teacher)
	filters = {"student": ["in", students or [""]]}
	if cint(unanswered):
		filters["response"] = ["is", "not set"]
	rows = frappe.get_all(
		"Parental Feedback",
		filters=filters,
		fields=["name", "student", "parent", "date", "feedback", "response", "teacher", "linked_document_type", "linked_document", "modified"],
		order_by="creation desc",
		limit_page_length=common.paginate(limit),
	)
	names = dict(
		frappe.get_all("Student", filters={"name": ["in", [r.student for r in rows] or [""]]}, fields=["name", "student_name"], as_list=True)
	)
	parents = dict(
		frappe.get_all("Guardian", filters={"name": ["in", [r.parent for r in rows if r.parent] or [""]]}, fields=["name", "guardian_name"], as_list=True)
	)
	for row in rows:
		row["student_name"] = names.get(row.student)
		row["parent_name"] = parents.get(row.parent)
		if not row.linked_document:
			row["linked_document_type"] = None
		row["feedback"] = strip_html(row.feedback or "")
		row["response"] = strip_html(row.response or "") or None
	return sync._stringify(rows)


@frappe.whitelist(methods=["POST"])
def respond_feedback(name: str, response: str) -> dict:
	row = frappe.db.get_value("Parental Feedback", name, ["student", "parent"], as_dict=True)
	if not row:
		raise frappe.DoesNotExistError(_("Message not found."))
	common.assert_teacher_of(row.student)
	response = cstr(response).strip()
	if len(response) < 2:
		frappe.throw(_("Write a reply first."))
	frappe.db.set_value(
		"Parental Feedback", name, {"response": _html(response[:4000]), "teacher": frappe.session.user}
	)
	email = frappe.db.get_value("Guardian", row.parent, "email_address") if row.parent else None
	if email:
		app = common.setting("app_name") or "CBC AI Tutor"
		common.notify(
			[email],
			_("{0}: a teacher replied about {1}").format(app, frappe.db.get_value("Student", row.student, "student_name")),
			_html(response[:4000]),
		)
	return {"name": name}
