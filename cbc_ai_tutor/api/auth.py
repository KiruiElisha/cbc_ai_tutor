"""Device sign-in for the apps.

A sign-in issues a random ``cbc_`` token. Only its SHA-256 is stored, on a
``CBC Device Session``, so a leaked database does not leak working tokens. The
token is sent as ``Authorization: Bearer cbc_...`` and resolved by
:func:`validate_token`, registered in ``auth_hooks``.

Sessions slide: each use pushes the expiry ``session_days`` forward, so a device in
daily use stays signed in and an abandoned one lapses.
"""

from __future__ import annotations

import hashlib
import secrets

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, get_datetime, now_datetime, time_diff_in_seconds, validate_email_address

from cbc_ai_tutor.api import common

TOKEN_PREFIX = "cbc_"
SESSION = "CBC Device Session"
TOUCH_EVERY_SECONDS = 15 * 60


def _hash(token: str) -> str:
	return hashlib.sha256(token.encode()).hexdigest()


def _bearer() -> str | None:
	parts = (frappe.get_request_header("Authorization", "") or "").split(" ")
	if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].startswith(TOKEN_PREFIX):
		return None
	return parts[1]


def validate_token():
	"""``auth_hooks`` entry: turn a device token into the request's user."""
	token = _bearer()
	if not token:
		return
	row = frappe.db.get_value(
		SESSION,
		{"token_hash": _hash(token)},
		["name", "user", "student", "role_type", "revoked", "expires_on", "last_seen"],
		as_dict=True,
	)
	now = now_datetime()
	if not row or row.revoked or (row.expires_on and get_datetime(row.expires_on) <= now):
		return
	if not frappe.db.get_value("User", row.user, "enabled"):
		return

	form_dict = frappe.local.form_dict
	frappe.set_user(row.user)
	frappe.local.form_dict = form_dict
	frappe.local.cbc_session = row

	if not row.last_seen or time_diff_in_seconds(now, row.last_seen) > TOUCH_EVERY_SECONDS:
		frappe.db.set_value(
			SESSION,
			row.name,
			{"last_seen": now, "expires_on": add_days(now, cint(common.setting("session_days", 90)) or 90)},
			update_modified=False,
		)


def _issue(user: str, role_type: str, student: str | None = None, device: dict | None = None) -> str:
	device = device or {}
	token = TOKEN_PREFIX + secrets.token_urlsafe(32)
	now = now_datetime()
	frappe.get_doc(
		{
			"doctype": SESSION,
			"user": user,
			"role_type": role_type,
			"student": student,
			"token_hash": _hash(token),
			"device_name": (device.get("device_name") or "")[:140],
			"platform": (device.get("platform") or "")[:140],
			"app_version": (device.get("app_version") or "")[:140],
			"last_seen": now,
			"expires_on": add_days(now, cint(common.setting("session_days", 90)) or 90),
		}
	).insert(ignore_permissions=True)
	return token


def _device(device_name=None, platform=None, app_version=None) -> dict:
	return {"device_name": device_name, "platform": platform, "app_version": app_version}


def profile(user: str | None = None, student: str | None = None) -> dict:
	"""Everything the app needs to decide which home screen to show."""
	user = user or frappe.session.user
	doc = frappe.db.get_value("User", user, ["name", "full_name", "email", "mobile_no", "user_image"], as_dict=True)
	roles = common.roles_for_user(user)
	out = {
		"user": doc.name,
		"full_name": doc.full_name,
		"email": "" if (doc.email or "").endswith("@" + _learner_domain()) else doc.email,
		"mobile_no": doc.mobile_no,
		"image": doc.user_image,
		"roles": roles,
		"server_time": str(now_datetime()),
	}
	guardian = common.guardian_for_user(user)
	if guardian:
		out["guardian"] = guardian
	teacher = common.instructor_for_user(user)
	if teacher:
		out["instructor"] = teacher
		out["school"] = frappe.db.get_value("Instructor", teacher, "custom_school")

	student = student or common.student_for_user(user)
	if student:
		out["learner"] = learner_card(student)
	return out


def learner_card(student: str) -> dict:
	row = frappe.db.get_value(
		"Student",
		student,
		["name", "student_name", "first_name", "custom_grade", "custom_school", "custom_learner_code", "image"],
		as_dict=True,
	)
	ent = common.entitlement_for_student(student)
	return {
		"student": row.name,
		"name": row.student_name,
		"first_name": row.first_name,
		"grade": row.custom_grade,
		"school": row.custom_school,
		"learner_code": row.custom_learner_code,
		"image": row.image,
		"entitled": ent.active,
		"subscription_status": ent.status,
		"access_until": str(ent.until) if ent.until else None,
	}


def _learner_domain() -> str:
	return (common.setting("learner_email_domain") or "learners.cbc.invalid").strip().lower()


def _primary_role(user: str, wanted: str | None) -> str:
	roles = common.roles_for_user(user)
	if wanted and wanted in roles:
		return wanted
	for role in (common.TEACHER, common.PARENT, common.LEARNER):
		if role in roles:
			return role
	frappe.throw(
		_("This account is not set up as a parent, teacher or learner yet."),
		frappe.PermissionError,
	)


def _find_user(login: str) -> str | None:
	login = (login or "").strip()
	if not login:
		return None
	if "@" in login:
		return frappe.db.get_value("User", {"email": login.lower()}, "name") or frappe.db.get_value(
			"User", {"name": login.lower()}, "name"
		)
	digits = "".join(ch for ch in login if ch.isdigit())
	candidates = {login, digits}
	if digits.startswith("0") and len(digits) == 10:
		candidates |= {"254" + digits[1:], "+254" + digits[1:]}
	if digits.startswith("254"):
		candidates |= {"0" + digits[3:], "+" + digits}
	for value in candidates:
		user = frappe.db.get_value("User", {"mobile_no": value}, "name")
		if user:
			return user
	return None


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=10 * 60)
def login(
	login: str,
	password: str,
	role: str | None = None,
	device_name: str | None = None,
	platform: str | None = None,
	app_version: str | None = None,
) -> dict:
	"""Email (or phone) and password, for parents and teachers."""
	from frappe.utils.password import check_password

	user = _find_user(login)
	try:
		if not user or user in ("Administrator", "Guest"):
			raise frappe.AuthenticationError
		check_password(user, password or "")
	except frappe.AuthenticationError:
		frappe.clear_messages()
		raise frappe.AuthenticationError(_("That email or password is not right."))
	if not frappe.db.get_value("User", user, "enabled"):
		raise frappe.AuthenticationError(_("This account has been switched off."))

	role_type = _primary_role(user, role)
	token = _issue(user, role_type, device=_device(device_name, platform, app_version))
	frappe.db.commit()
	return {"token": token, "role": role_type, "profile": profile(user)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(key="code", limit=8, seconds=15 * 60)
def learner_login(
	code: str,
	pin: str,
	device_name: str | None = None,
	platform: str | None = None,
	app_version: str | None = None,
) -> dict:
	"""Learner code and PIN. For children who have no email."""
	code = (code or "").strip().upper().replace("-", "").replace(" ", "")
	row = frappe.db.get_value(
		"Student",
		{"custom_learner_code": code},
		["name", "user", "enabled", "custom_pin_hash"],
		as_dict=True,
	)
	if not row or not row.enabled or not common.verify_pin(str(pin or ""), row.custom_pin_hash):
		raise frappe.AuthenticationError(_("That learner code or PIN is not right."))
	if not row.user:
		raise frappe.AuthenticationError(_("Ask your parent to open your profile once from their app."))

	token = _issue(row.user, common.LEARNER, student=row.name, device=_device(device_name, platform, app_version))
	frappe.db.commit()
	return {"token": token, "role": common.LEARNER, "profile": profile(row.user, row.name)}


@frappe.whitelist(methods=["POST"])
def open_learner(student: str, device_name: str | None = None, platform: str | None = None) -> dict:
	"""A parent hands their device to a child: a learner session on the same device."""
	common.assert_parent_of(student)
	if not frappe.db.get_value("Student", student, "enabled"):
		frappe.throw(_("This learner's profile is switched off."))
	token = _issue(frappe.session.user, common.LEARNER, student=student, device=_device(device_name, platform))
	frappe.db.commit()
	return {"token": token, "role": common.LEARNER, "profile": profile(frappe.session.user, student)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def signup_parent(
	full_name: str,
	email: str,
	phone: str,
	password: str,
	device_name: str | None = None,
	platform: str | None = None,
	app_version: str | None = None,
) -> dict:
	"""A parent account, its Guardian record and a free trial."""
	from frappe.utils.password_strength import test_password_strength

	full_name = (full_name or "").strip()
	email = (email or "").strip().lower()
	if len(full_name) < 2:
		frappe.throw(_("Enter your name."))
	if not validate_email_address(email):
		frappe.throw(_("Enter a valid email address."))
	if email.endswith("@" + _learner_domain()):
		frappe.throw(_("Use your own email address."))
	phone = common.normalize_phone(phone)
	if not password or len(password) < 8:
		frappe.throw(_("Use a password of at least 8 characters."))
	strength = test_password_strength(password, user_inputs=(full_name, email, phone))
	if strength and cint(strength.get("score")) < 2:
		frappe.throw(_("That password is too easy to guess. Add more words or characters."))

	result = provision_parent(
		full_name, email, phone, password, _device(device_name, platform, app_version), ignore_policy=False
	)
	frappe.db.commit()
	return result


def provision_parent(full_name: str, email: str, phone: str, password: str, device: dict, ignore_policy: bool = False) -> dict:
	"""A new parent: User, Guardian, free trial and a device token. Caller commits."""
	_reject_existing_parent(email, phone)
	first, _sep, last = full_name.partition(" ")
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first,
			"last_name": last or None,
			"mobile_no": phone,
			"user_type": "Website User",
			"send_welcome_email": 0,
			"enabled": 1,
		}
	)
	user.flags.ignore_permissions = True
	user.flags.ignore_password_policy = ignore_policy
	user.new_password = password
	user.insert()
	user.add_roles("Guardian")
	guardian = frappe.get_doc(
		{
			"doctype": "Guardian",
			"guardian_name": full_name,
			"email_address": email,
			"mobile_number": phone,
			"user": user.name,
		}
	).insert(ignore_permissions=True)
	common.start_trial(guardian.name, user.name)
	token = _issue(user.name, common.PARENT, device=device)
	return {"token": token, "role": common.PARENT, "profile": profile(user.name)}


def _reject_existing_parent(email: str, phone: str):
	if frappe.db.exists("User", email) or frappe.db.exists("User", {"email": email}):
		frappe.throw(
			_("An account already uses {0}. Sign in instead.").format(email),
			frappe.DuplicateEntryError,
		)
	if frappe.db.exists("User", {"mobile_no": phone}):
		frappe.throw(_("An account already uses that phone number."), frappe.DuplicateEntryError)


def issue_for(user: str, role: str | None, device: dict | None = None) -> dict:
	"""A device token for an account that is already a parent or a teacher."""
	if not frappe.db.get_value("User", user, "enabled"):
		raise frappe.AuthenticationError(_("This account has been switched off."))
	role_type = _primary_role(user, role)
	token = _issue(user, role_type, device=device or {})
	return {"token": token, "role": role_type, "profile": profile(user)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def request_password_reset(email: str) -> dict:
	"""Frappe's own reset: emails a one-time link. Same reply whether or not the account exists."""
	from frappe.core.doctype.user.user import reset_password

	user = _find_user(email)
	if user and not (frappe.db.get_value("User", user, "email") or "").endswith("@" + _learner_domain()):
		try:
			reset_password(user)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Password reset email for {user} failed")
	frappe.clear_messages()
	return {"message": _("If that account exists, we have emailed a link to reset the password.")}


@frappe.whitelist(methods=["POST"])
def change_password(old_password: str, new_password: str) -> dict:
	from frappe.utils.password import check_password, update_password

	user = common.require_login()
	if common.device_session() and common.device_session().get("student"):
		frappe.throw(_("Learners change their PIN through a parent."), frappe.PermissionError)
	try:
		check_password(user, old_password or "")
	except frappe.AuthenticationError:
		frappe.clear_messages()
		raise frappe.AuthenticationError(_("Your current password is not right."))
	if not new_password or len(new_password) < 8:
		frappe.throw(_("Use a password of at least 8 characters."))
	update_password(user, new_password)
	current = common.device_session()
	sessions = frappe.get_all(SESSION, filters={"user": user, "revoked": 0}, pluck="name")
	for name in sessions:
		if not current or name != current.name:
			frappe.db.set_value(SESSION, name, "revoked", 1, update_modified=False)
	return {"message": _("Password changed. Other devices have been signed out.")}


@frappe.whitelist(methods=["POST"])
def logout() -> dict:
	session = common.device_session()
	if session:
		frappe.db.set_value(SESSION, session.name, "revoked", 1, update_modified=False)
	return {"ok": True}


@frappe.whitelist()
def me() -> dict:
	common.require_login()
	session = common.device_session()
	student = session.student if session and session.get("student") else None
	if student:
		common.current_learner()
	return {"role": session.role_type if session else None, "profile": profile(frappe.session.user, student)}


@frappe.whitelist()
def devices() -> list[dict]:
	user = common.require_login()
	current = common.device_session()
	rows = frappe.get_all(
		SESSION,
		filters={"user": user, "revoked": 0, "expires_on": [">", now_datetime()]},
		fields=["name", "device_name", "platform", "role_type", "student", "last_seen", "creation"],
		order_by="last_seen desc",
	)
	for row in rows:
		row["current"] = bool(current and current.name == row.name)
	return rows


@frappe.whitelist(methods=["POST"])
def sign_out_device(name: str) -> dict:
	user = common.require_login()
	if frappe.db.get_value(SESSION, name, "user") != user:
		raise frappe.PermissionError(_("That device is not yours."))
	frappe.db.set_value(SESSION, name, "revoked", 1, update_modified=False)
	return {"ok": True}
