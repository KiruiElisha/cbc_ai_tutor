"""The parent experience: children, their progress, messages to teachers."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, getdate, nowdate, strip_html

from cbc_ai_tutor.api import common, progress, sync
from cbc_ai_tutor.api.auth import _learner_domain, learner_card

GENDERS = ("Male", "Female")


@frappe.whitelist()
def dashboard() -> dict:
	guardian = common.current_parent()
	state = common.subscription_state(common.subscription_for(guardian))
	children = []
	for student in _children(guardian):
		card = learner_card(student)
		card["enabled"] = frappe.db.get_value("Student", student, "enabled")
		card.update(progress.summary(student))
		children.append(card)
	unread = frappe.db.count(
		"Parental Feedback",
		{"parent": guardian, "response": ["is", "set"], "modified": [">=", getdate(nowdate()).replace(day=1)]},
	)
	return {
		"guardian": guardian,
		"guardian_name": frappe.db.get_value("Guardian", guardian, "guardian_name"),
		"subscription": {
			"active": 1 if state.active else 0,
			"status": state.status,
			"plan": state.plan,
			"until": str(state.until) if state.until else None,
			"max_learners": state.max_learners,
		},
		"children": children,
		"replies_this_month": unread,
	}


def _children(guardian: str) -> list[str]:
	names = common.children_of(guardian)
	return frappe.get_all(
		"Student", filters={"name": ["in", names or [""]]}, order_by="first_name asc", pluck="name"
	)


def _active_children(guardian: str) -> int:
	names = common.children_of(guardian)
	return frappe.db.count("Student", {"name": ["in", names or [""]], "enabled": 1})


def _capacity(guardian: str) -> int:
	state = common.subscription_state(common.subscription_for(guardian))
	if state.active:
		return state.max_learners
	return cint(common.setting("trial_max_learners", 3))


def _clean_grade(grade: str | None) -> str | None:
	if grade and not frappe.db.exists("Program", grade):
		frappe.throw(_("Pick a grade from the list."))
	return grade or None


def _clean_school(school: str | None) -> str | None:
	if school and not frappe.db.exists("School", {"name": school, "is_active": 1}):
		frappe.throw(_("Pick a school from the list, or leave it empty."))
	return school or None


def _clean_gender(gender: str | None) -> str | None:
	if not gender:
		return None
	if gender not in GENDERS or not frappe.db.exists("Gender", gender):
		return None
	return gender


@frappe.whitelist(methods=["POST"])
def add_child(
	first_name: str,
	grade: str,
	pin: str,
	last_name: str | None = None,
	school: str | None = None,
	date_of_birth: str | None = None,
	gender: str | None = None,
	relation: str | None = None,
) -> dict:
	"""A learner profile with its own code and PIN, so the child can sign in on any device."""
	guardian = common.current_parent()
	first_name = (first_name or "").strip()
	last_name = (last_name or "").strip() or None
	if len(first_name) < 2:
		frappe.throw(_("Enter the child's first name."))
	grade = _clean_grade(grade)
	if not grade:
		frappe.throw(_("Pick the child's grade."))
	school = _clean_school(school)
	pin = common.validate_pin(pin)
	if date_of_birth and getdate(date_of_birth) >= getdate(nowdate()):
		frappe.throw(_("Check the date of birth."))

	limit = _capacity(guardian)
	if _active_children(guardian) >= limit:
		frappe.throw(
			_("Your plan covers {0} learners. Upgrade it, or switch off a learner you no longer need.").format(limit),
			common.SubscriptionRequired,
		)

	code = common.new_learner_code()
	email = f"learner-{code.lower()}@{_learner_domain()}"
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"user_type": "Website User",
			"send_welcome_email": 0,
			"enabled": 1,
		}
	)
	user.flags.ignore_permissions = True
	user.flags.no_welcome_mail = True
	user.insert()
	user.add_roles("Student")

	guardian_name = frappe.db.get_value("Guardian", guardian, "guardian_name")
	student = frappe.get_doc(
		{
			"doctype": "Student",
			"first_name": first_name,
			"last_name": last_name,
			"student_email_id": email,
			"user": user.name,
			"enabled": 1,
			"joining_date": nowdate(),
			"date_of_birth": date_of_birth or None,
			"gender": _clean_gender(gender),
			"custom_grade": grade,
			"custom_school": school,
			"custom_learner_code": code,
			"custom_pin_hash": common.hash_pin(pin),
			"guardians": [
				{
					"guardian": guardian,
					"guardian_name": guardian_name,
					"relation": relation if relation in ("Mother", "Father", "Others") else None,
				}
			],
		}
	)
	student.flags.ignore_permissions = True
	with common.as_administrator():
		student.insert()
	frappe.db.commit()

	card = learner_card(student.name)
	card["enabled"] = 1
	return {"learner": card, "learner_code": code}


@frappe.whitelist(methods=["POST"])
def update_child(
	student: str,
	first_name: str | None = None,
	last_name: str | None = None,
	grade: str | None = None,
	school: str | None = None,
	date_of_birth: str | None = None,
	gender: str | None = None,
) -> dict:
	common.assert_parent_of(student)
	doc = frappe.get_doc("Student", student)
	if first_name is not None:
		if len(first_name.strip()) < 2:
			frappe.throw(_("Enter the child's first name."))
		doc.first_name = first_name.strip()
	if last_name is not None:
		doc.last_name = last_name.strip() or None
	if grade:
		doc.custom_grade = _clean_grade(grade)
	if school is not None:
		doc.custom_school = _clean_school(school)
	if date_of_birth is not None:
		doc.date_of_birth = date_of_birth or None
	if gender is not None:
		doc.gender = _clean_gender(gender)
	doc.flags.ignore_permissions = True
	with common.as_administrator():
		doc.save()
	if doc.user:
		frappe.db.set_value("User", doc.user, {"first_name": doc.first_name, "last_name": doc.last_name})
	return learner_card(student)


@frappe.whitelist(methods=["POST"])
def set_child_pin(student: str, pin: str) -> dict:
	"""New PIN. Devices the child is signed in on are signed out."""
	common.assert_parent_of(student)
	pin = common.validate_pin(pin)
	frappe.db.set_value("Student", student, "custom_pin_hash", common.hash_pin(pin))
	_sign_out_learner(student)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def set_child_enabled(student: str, enabled: int | str) -> dict:
	"""Switching a learner off frees a place on the plan; their history is kept."""
	guardian = common.assert_parent_of(student)
	enabled = 1 if cint(enabled) else 0
	current = cint(frappe.db.get_value("Student", student, "enabled"))
	if enabled and not current and _active_children(guardian) >= _capacity(guardian):
		frappe.throw(_("Your plan has no free learner place. Upgrade it first."), common.SubscriptionRequired)
	frappe.db.set_value("Student", student, "enabled", enabled)
	user = frappe.db.get_value("Student", student, "user")
	if user and (user or "").endswith("@" + _learner_domain()):
		frappe.db.set_value("User", user, "enabled", enabled)
	if not enabled:
		_sign_out_learner(student)
	return {"student": student, "enabled": enabled}


def _sign_out_learner(student: str):
	for name in frappe.get_all(
		"CBC Device Session", filters={"student": student, "revoked": 0}, pluck="name"
	):
		frappe.db.set_value("CBC Device Session", name, "revoked", 1)


@frappe.whitelist()
def child_progress(student: str) -> dict:
	common.assert_parent_of(student)
	report = progress.report(student)
	report["learner"]["enabled"] = cint(frappe.db.get_value("Student", student, "enabled"))
	return report


@frappe.whitelist()
def child_conversations(student: str, limit: int = 20) -> list[dict]:
	"""What the child asked the AI tutor, so parents can see how it is used."""
	common.assert_parent_of(student)
	rows = frappe.get_all(
		"AI Tutor Interaction",
		filters={"student": student},
		fields=["name", "date", "topic", "question", "lesson", "conversation"],
		order_by="date desc",
		limit_page_length=common.paginate(limit, 20, 100),
	)
	for row in rows:
		row["question"] = strip_html(row.question or "")[:400]
	return sync._stringify(rows)


# ---------------------------------------------------------------------------
# Messages to teachers
# ---------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def send_feedback(student: str, message: str, linked_document_type: str | None = None, linked_document: str | None = None) -> dict:
	guardian = common.assert_parent_of(student)
	message = (message or "").strip()
	if len(message) < 3:
		frappe.throw(_("Write a message first."))
	if len(message) > 4000:
		frappe.throw(_("Keep the message under 4000 characters."))
	if linked_document_type not in (None, "", "Portfolio Entry", "Continuous Assessment"):
		frappe.throw(_("That record cannot be linked to a message."))
	if linked_document_type and linked_document:
		if frappe.db.get_value(linked_document_type, linked_document, "student") != student:
			frappe.throw(_("That record is not about this learner."))
	else:
		linked_document_type = linked_document = None

	teacher_user = None
	if linked_document_type and linked_document:
		teacher_user = frappe.db.get_value(linked_document_type, linked_document, "teacher")

	doc = frappe.get_doc(
		{
			"doctype": "Parental Feedback",
			"student": student,
			"parent": guardian,
			"date": nowdate(),
			"feedback": frappe.utils.escape_html(message).replace("\n", "<br>"),
			"linked_document_type": linked_document_type,
			"linked_document": linked_document,
			"teacher": teacher_user,
		}
	).insert(ignore_permissions=True)
	return {"name": doc.name}


@frappe.whitelist()
def feedback(student: str | None = None, limit: int = 50) -> list[dict]:
	guardian = common.current_parent()
	filters = {"parent": guardian}
	if student:
		common.assert_parent_of(student)
		filters["student"] = student
	rows = frappe.get_all(
		"Parental Feedback",
		filters=filters,
		fields=["name", "student", "date", "feedback", "response", "teacher", "linked_document_type", "linked_document", "modified"],
		order_by="creation desc",
		limit_page_length=common.paginate(limit),
	)
	names = dict(
		frappe.get_all("Student", filters={"name": ["in", [r.student for r in rows] or [""]]}, fields=["name", "student_name"], as_list=True)
	)
	for row in rows:
		row["student_name"] = names.get(row.student)
		if not row.linked_document:
			row["linked_document_type"] = None
		row["feedback"] = strip_html(row.feedback or "")
		row["response"] = strip_html(row.response or "") or None
	return sync._stringify(rows)
