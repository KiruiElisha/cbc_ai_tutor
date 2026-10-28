"""Who is calling, and what they may touch."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, now_datetime

LEARNER = "Learner"
PARENT = "Parent"
TEACHER = "Teacher"

SETTINGS = "CBC Settings"

PIN_ITERATIONS = 120_000


class SubscriptionRequired(frappe.PermissionError):
	"""The family has no active trial or plan. The app shows the plans screen."""

	http_status_code = 402


class QuotaExceeded(frappe.ValidationError):
	"""Today's AI tutor messages are used up."""

	http_status_code = 429


def settings():
	return frappe.get_cached_doc(SETTINGS)


def setting(fieldname: str, default=None):
	value = frappe.db.get_single_value(SETTINGS, fieldname)
	return default if value in (None, "") else value


def secret(fieldname: str) -> str:
	"""A Password field from CBC Settings, decrypted."""
	from frappe.utils.password import get_decrypted_password

	return get_decrypted_password(SETTINGS, SETTINGS, fieldname, raise_exception=False) or ""


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def device_session() -> frappe._dict | None:
	"""The device session the auth hook resolved for this request, if any."""
	return getattr(frappe.local, "cbc_session", None)


@contextmanager
def as_administrator():
	"""For Education controllers that save linked records without `ignore_permissions`."""
	user = frappe.session.user
	form_dict = frappe.local.form_dict
	session = device_session()
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)
		frappe.local.form_dict = form_dict
		if session is not None:
			frappe.local.cbc_session = session


def notify(recipients: list[str], subject: str, message: str) -> bool:
	"""Queue an email. A missing or broken mail set-up must not undo the action that sent it."""
	recipients = [r for r in recipients if r and not r.endswith("@" + (setting("learner_email_domain") or "learners.cbc.invalid"))]
	if not recipients:
		return False
	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=message, delayed=True)
		return True
	except Exception:
		frappe.clear_messages()
		frappe.log_error(title=f"Email not sent: {subject}"[:140])
		return False


def require_login() -> str:
	user = frappe.session.user
	if not user or user == "Guest":
		raise frappe.AuthenticationError(_("Please sign in."))
	return user


def guardian_for_user(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	return frappe.db.get_value("Guardian", {"user": user}, "name")


def student_for_user(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	return frappe.db.get_value("Student", {"user": user, "enabled": 1}, "name")


def instructor_for_user(user: str | None = None) -> str | None:
	user = user or frappe.session.user
	if frappe.get_meta("Instructor").has_field("custom_email"):
		name = frappe.db.get_value("Instructor", {"custom_email": user, "status": "Active"}, "name")
		if name:
			return name
	if frappe.db.exists("DocType", "Employee"):
		employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
		if employee:
			return frappe.db.get_value("Instructor", {"employee": employee, "status": "Active"}, "name")
	return None


def roles_for_user(user: str | None = None) -> list[str]:
	"""Which app experiences this account can open."""
	user = user or frappe.session.user
	roles = []
	if instructor_for_user(user):
		roles.append(TEACHER)
	if guardian_for_user(user):
		roles.append(PARENT)
	if student_for_user(user):
		roles.append(LEARNER)
	return roles


def current_learner() -> str:
	"""The learner this request acts for.

	A device opened on a learner's profile carries the learner on its session. A
	parent's session only gets there through :func:`auth.open_learner`, which
	checked the link; it is checked again here in case the link was removed since.
	"""
	require_login()
	session = device_session()
	if session and session.get("student"):
		student = session.student
		if not frappe.db.get_value("Student", student, "enabled"):
			raise frappe.PermissionError(_("This learner's profile has been switched off."))
		learner_user = frappe.db.get_value("Student", student, "user")
		if learner_user != frappe.session.user:
			guardian = guardian_for_user()
			if not guardian or not is_guardian_of(guardian, student):
				raise frappe.PermissionError(_("You are no longer linked to this learner."))
		return student

	student = student_for_user()
	if not student:
		raise frappe.PermissionError(_("Open a learner profile first."))
	return student


def current_parent() -> str:
	require_login()
	guardian = guardian_for_user()
	if not guardian:
		raise frappe.PermissionError(_("This account is not a parent account."))
	return guardian


def current_teacher() -> frappe._dict:
	require_login()
	instructor = instructor_for_user()
	if not instructor:
		raise frappe.PermissionError(_("This account is not a teacher account."))
	school = None
	if frappe.get_meta("Instructor").has_field("custom_school"):
		school = frappe.db.get_value("Instructor", instructor, "custom_school")
	return frappe._dict(name=instructor, school=school, user=frappe.session.user)


def is_guardian_of(guardian: str, student: str) -> bool:
	return bool(
		frappe.db.exists(
			"Student Guardian",
			{"parent": student, "parenttype": "Student", "guardian": guardian},
		)
	)


def children_of(guardian: str) -> list[str]:
	return frappe.get_all(
		"Student Guardian",
		filters={"guardian": guardian, "parenttype": "Student"},
		pluck="parent",
		distinct=True,
	)


def guardians_of(student: str) -> list[str]:
	return frappe.get_all(
		"Student Guardian",
		filters={"parent": student, "parenttype": "Student"},
		pluck="guardian",
		distinct=True,
	)


def assert_parent_of(student: str) -> str:
	guardian = current_parent()
	if not student or not is_guardian_of(guardian, student):
		raise frappe.PermissionError(_("That learner is not on your account."))
	return guardian


def assert_teacher_of(student: str) -> frappe._dict:
	teacher = current_teacher()
	if not student or not frappe.db.exists("Student", student):
		raise frappe.DoesNotExistError(_("Learner not found."))
	if not teacher.school:
		raise frappe.PermissionError(_("Your teacher profile has no school, so no learners are visible yet."))
	if frappe.db.get_value("Student", student, "custom_school") != teacher.school:
		raise frappe.PermissionError(_("That learner is not in your school."))
	return teacher


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


def subscription_for(guardian: str) -> frappe._dict | None:
	return frappe.db.get_value(
		"Parent Subscription",
		{"guardian": guardian},
		[
			"name",
			"status",
			"plan",
			"current_period_start",
			"current_period_end",
			"trial_ends_on",
			"max_learners",
			"ai_messages_per_day",
		],
		as_dict=True,
	)


def subscription_state(sub: frappe._dict | None) -> frappe._dict:
	"""Whether a subscription opens the paid content right now, and its limits."""
	now = now_datetime()
	state = frappe._dict(
		active=False,
		status="None",
		plan=None,
		until=None,
		max_learners=0,
		ai_messages_per_day=0,
		subscription=None,
	)
	if not sub:
		return state
	state.subscription = sub.name
	state.plan = sub.plan
	state.status = sub.status

	if sub.status == "Active" and sub.current_period_end and get_datetime(sub.current_period_end) > now:
		state.active = True
		state.until = sub.current_period_end
	elif sub.status == "Trial" and sub.trial_ends_on and get_datetime(sub.trial_ends_on) > now:
		state.active = True
		state.until = sub.trial_ends_on
	elif sub.status in ("Active", "Trial"):
		state.status = "Expired"
		state.until = sub.current_period_end or sub.trial_ends_on

	if sub.status == "Trial":
		state.max_learners = cint(setting("trial_max_learners", 3))
		state.ai_messages_per_day = cint(setting("trial_ai_messages_per_day", 20))
	else:
		state.max_learners = cint(sub.max_learners) or 1
		state.ai_messages_per_day = cint(sub.ai_messages_per_day)
	return state


def entitlement_for_student(student: str) -> frappe._dict:
	"""The best subscription among the learner's parents."""
	best = subscription_state(None)
	for guardian in guardians_of(student):
		state = subscription_state(subscription_for(guardian))
		if state.active and (not best.active or str(state.until) > str(best.until)):
			best = state
		elif not best.active and state.status != "None":
			best = state
	return best


def start_trial(guardian: str, user: str) -> str:
	existing = frappe.db.get_value("Parent Subscription", {"guardian": guardian}, "name")
	if existing:
		return existing
	days = cint(setting("trial_days", 7))
	now = now_datetime()
	doc = frappe.get_doc(
		{
			"doctype": "Parent Subscription",
			"guardian": guardian,
			"user": user,
			"status": "Trial" if days > 0 else "Expired",
			"trial_ends_on": add_days(now, days) if days > 0 else now,
			"current_period_start": now,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------------------
# PINs and codes
# ---------------------------------------------------------------------------


def hash_pin(pin: str) -> str:
	salt = secrets.token_hex(16)
	digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), PIN_ITERATIONS).hex()
	return f"pbkdf2_sha256${PIN_ITERATIONS}${salt}${digest}"


def verify_pin(pin: str, stored: str | None) -> bool:
	if not stored or not pin:
		return False
	try:
		_algo, iterations, salt, digest = stored.split("$")
		check = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), int(iterations)).hex()
	except ValueError:
		return False
	return hmac.compare_digest(check, digest)


def validate_pin(pin) -> str:
	pin = str(pin or "").strip()
	if not pin.isdigit() or not 4 <= len(pin) <= 8:
		frappe.throw(_("A PIN is 4 to 8 digits."))
	if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
		frappe.throw(_("Pick a PIN that is harder to guess than {0}.").format(pin))
	return pin


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_learner_code() -> str:
	for _attempt in range(20):
		code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
		if not frappe.db.exists("Student", {"custom_learner_code": code}):
			return code
	frappe.throw(_("Could not create a learner code. Try again."))


def normalize_phone(phone: str) -> str:
	"""Kenyan mobile numbers in the 2547XXXXXXXX / 2541XXXXXXXX form."""
	digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
	if digits.startswith("0") and len(digits) == 10:
		digits = "254" + digits[1:]
	elif len(digits) == 9 and digits[0] in "17":
		digits = "254" + digits
	if not (len(digits) == 12 and digits.startswith("254") and digits[3] in "17"):
		frappe.throw(_("Enter a Safaricom number like 0712 345 678."))
	return digits


def paginate(limit, default: int = 50, ceiling: int = 200) -> int:
	return max(1, min(cint(limit) or default, ceiling))
