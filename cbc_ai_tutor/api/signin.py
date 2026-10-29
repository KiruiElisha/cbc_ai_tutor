"""Sign-in without a password: a 6-digit email code, or Google.

Learners stay on their code and PIN. A Google account or an email code can open
a parent account (and start the trial) or sign in a teacher the school already
created. The browser step hands the app a one-time code, never the device token.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint, escape_html, validate_email_address

from cbc_ai_tutor.api import auth, common

CODE_MINUTES = 10
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"


def _cache():
	return frappe.cache()


def _email(value: str) -> str:
	email = (value or "").strip().lower()
	if not validate_email_address(email) or email.endswith("@" + auth._learner_domain()):
		frappe.throw(_("Enter the email address you use."))
	return email


def _role(role: str | None) -> str:
	if role not in (common.PARENT, common.TEACHER):
		frappe.throw(_("Choose parent or teacher."))
	return role


def _device(device_name=None, platform=None, app_version=None) -> dict:
	return auth._device(device_name, platform, app_version)


def _handoff(result: dict) -> str:
	code = secrets.token_urlsafe(24)
	_cache().set_value(f"cbc_handoff:{code}", result, expires_in_sec=120)
	return code


def _page(title: str, message: str, link: str | None = None, link_label: str | None = None, form: str = ""):
	app = escape_html(common.setting("app_name") or "CBC Tutor")
	button = ""
	if link:
		button = f'<a href="{escape_html(link)}">{escape_html(link_label or _("Open the app"))}</a>'
	html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{app}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f8fafc;margin:0;display:grid;place-items:center;min-height:100vh}}
.card{{background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,.1);padding:28px;max-width:420px;width:92%}}
h1{{color:#0f766e;font-size:22px;margin:0 0 12px}}p,label{{color:#334155;line-height:1.5}}
input{{width:100%;box-sizing:border-box;padding:12px;border:1px solid #cbd5e1;border-radius:10px;font:inherit;margin:4px 0 14px}}
button,a{{display:block;text-align:center;background:#0f766e;color:#fff;padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600;border:0;font:inherit}}</style>
</head><body><div class="card"><h1>{escape_html(title)}</h1><p>{message}</p>{form}{button}</div></body></html>"""
	frappe.local.response["type"] = "download"
	frappe.local.response["content_type"] = "text/html; charset=utf-8"
	frappe.local.response["filename"] = "signin.html"
	frappe.local.response["filecontent"] = html.encode()
	frappe.local.response["display_content_as"] = "inline"


def _open_app(result: dict, message: str):
	code = _handoff(result)
	_page(_("You're signed in"), message, f"cbctutor://auth?code={code}", _("Open CBC Tutor"))


# ---------------------------------------------------------------------------
# Email code
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def options() -> dict:
	return {"google": 1 if cint(common.setting("google_enabled")) and common.setting("google_client_id") else 0}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def request_email_code(email: str, role: str = "Parent") -> dict:
	"""Email a 6-digit code. Parents can be new; teachers must already exist."""
	email = _email(email)
	role = _role(role)
	user = frappe.db.get_value("User", {"email": email}, "name")
	quiet = _("If that email can sign in, a 6-digit code is on its way.")
	if role == common.TEACHER and not (user and common.instructor_for_user(user)):
		return {"message": quiet}

	code = f"{secrets.randbelow(1_000_000):06d}"
	_cache().set_value(
		f"cbc_email_code:{email}",
		{"hash": hashlib.sha256(f"{email}:{code}".encode()).hexdigest(), "role": role, "tries": 0},
		expires_in_sec=CODE_MINUTES * 60,
	)
	app = common.setting("app_name") or "CBC Tutor"
	sent = common.notify(
		[email],
		_("{0} sign-in code").format(app),
		f"<p>{escape_html(_('Your sign-in code is'))}</p>"
		f"<p style='font-size:28px;letter-spacing:0.25em;font-weight:700'>{code}</p>"
		f"<p>{escape_html(_('It works for {0} minutes. If you did not ask, ignore this email.').format(CODE_MINUTES))}</p>",
	)
	if not sent:
		frappe.throw(_("The email could not be sent. Use Google, or ask the school to set up email."))
	frappe.db.commit()
	if role == common.PARENT:
		return {"message": _("We sent a 6-digit code. It works for {0} minutes.").format(CODE_MINUTES)}
	return {"message": quiet}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=15 * 60)
def confirm_email_code(
	email: str,
	code: str,
	role: str = "Parent",
	full_name: str | None = None,
	phone: str | None = None,
	device_name: str | None = None,
	platform: str | None = None,
	app_version: str | None = None,
) -> dict:
	email = _email(email)
	role = _role(role)
	key = f"cbc_email_code:{email}"
	row = _cache().get_value(key)
	digest = hashlib.sha256(f"{email}:{str(code or '').strip()}".encode()).hexdigest()
	expected = (row or {}).get("hash") or ""
	if not row or len(expected) != len(digest) or not secrets.compare_digest(expected, digest):
		if row:
			row["tries"] = cint(row.get("tries")) + 1
			if row["tries"] >= 5:
				_cache().delete_value(key)
			else:
				_cache().set_value(key, row, expires_in_sec=CODE_MINUTES * 60)
		frappe.throw(_("That code is not right, or it has expired."))

	role = _role(row.get("role") or role)
	user = frappe.db.get_value("User", {"email": email}, "name")
	device = _device(device_name, platform, app_version)
	if role == common.TEACHER:
		if not user or not common.instructor_for_user(user):
			frappe.throw(_("That email is not a teacher at a school yet."))
		result = auth.issue_for(user, role, device)
	elif user and common.guardian_for_user(user):
		result = auth.issue_for(user, role, device)
	elif user:
		frappe.throw(_("That email is already used by another account."))
	else:
		full_name = (full_name or "").strip()
		if len(full_name) < 2 or not phone:
			return {"needs_profile": True}
		result = auth.provision_parent(
			full_name, email, common.normalize_phone(phone), secrets.token_urlsafe(24), device, ignore_policy=True
		)
	_cache().delete_value(key)
	frappe.db.commit()
	return result


# ---------------------------------------------------------------------------
# Google
# ---------------------------------------------------------------------------


def _google_redirect() -> str:
	return f"{frappe.utils.get_url()}/api/method/cbc_ai_tutor.api.signin.google_callback"


def _google_ready():
	if not (cint(common.setting("google_enabled")) and common.setting("google_client_id") and common.secret("google_client_secret")):
		frappe.throw(_("Google sign-in is not available right now."))


@frappe.whitelist(allow_guest=True)
def google_url(
	role: str = "Parent",
	device_name: str | None = None,
	platform: str | None = None,
	app_version: str | None = None,
) -> dict:
	"""The Google page the app opens in the browser."""
	_google_ready()
	role = _role(role)
	verifier = secrets.token_urlsafe(64)
	challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
	state = secrets.token_urlsafe(24)
	_cache().set_value(
		f"cbc_google:{state}",
		{"verifier": verifier, "role": role, "device": _device(device_name, platform, app_version)},
		expires_in_sec=CODE_MINUTES * 60,
	)
	query = urlencode(
		{
			"client_id": common.setting("google_client_id"),
			"redirect_uri": _google_redirect(),
			"response_type": "code",
			"scope": "openid email profile",
			"state": state,
			"code_challenge": challenge,
			"code_challenge_method": "S256",
			"prompt": "select_account",
		}
	)
	return {"url": f"{GOOGLE_AUTH}?{query}"}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None, **kwargs):
	if error or not code or not state:
		return _page(_("Google sign-in stopped"), _("Nothing was changed. Go back to the app and try again."))
	pending = _cache().get_value(f"cbc_google:{state}")
	_cache().delete_value(f"cbc_google:{state}")
	if not pending:
		return _page(_("That sign-in expired"), _("Go back to the app and start again."))
	try:
		_google_ready()
		token = requests.post(
			GOOGLE_TOKEN,
			data={
				"code": code,
				"client_id": common.setting("google_client_id"),
				"client_secret": common.secret("google_client_secret"),
				"redirect_uri": _google_redirect(),
				"grant_type": "authorization_code",
				"code_verifier": pending["verifier"],
			},
			timeout=20,
		).json()
		access = token.get("access_token")
		if not access:
			frappe.throw(_("Google did not confirm the sign-in."))
		info = requests.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access}"}, timeout=20).json()
		if not info.get("email_verified"):
			frappe.throw(_("That Google account has no confirmed email address."))
		email = _email(info.get("email"))
		name = (info.get("name") or email.split("@")[0]).strip()
		result = _google_account(email, name, pending["role"], pending["device"])
	except (frappe.ValidationError, frappe.AuthenticationError, frappe.DuplicateEntryError) as e:
		frappe.db.rollback()
		return _page(_("Could not sign in with Google"), escape_html(str(e)))
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="Google sign-in failed", message=frappe.get_traceback())
		return _page(_("Could not sign in with Google"), _("Something went wrong. Go back to the app and try again."))
	if result.get("needs_phone"):
		ticket = secrets.token_urlsafe(24)
		_cache().set_value(
			f"cbc_google_new:{ticket}",
			{"email": email, "name": name, "device": pending["device"]},
			expires_in_sec=CODE_MINUTES * 60,
		)
		form = f"""<form method="POST" action="/api/method/cbc_ai_tutor.api.signin.google_finish">
<input type="hidden" name="csrf_token" value="{escape_html(frappe.sessions.get_csrf_token())}">
<input type="hidden" name="ticket" value="{escape_html(ticket)}">
<label>{escape_html(_("Your name"))}<input name="full_name" value="{escape_html(name)}" required></label>
<label>{escape_html(_("M-Pesa phone number"))}<input name="phone" inputmode="tel" placeholder="0712 345 678" required></label>
<button type="submit">{escape_html(_("Continue"))}</button></form>"""
		return _page(_("One more step"), _("Add the number you will pay with, then the app opens."), form=form)
	frappe.db.commit()
	return _open_app(result, _("You can go back to CBC Tutor."))


def _google_account(email: str, name: str, role: str, device: dict) -> dict:
	user = frappe.db.get_value("User", {"email": email}, "name")
	if role == common.TEACHER:
		if not user or not common.instructor_for_user(user):
			frappe.throw(_("That Google account is not a teacher yet. Ask the school to add you."))
		return auth.issue_for(user, role, device)
	if user and common.guardian_for_user(user):
		return auth.issue_for(user, common.PARENT, device)
	if user:
		frappe.throw(_("That email is already used by another account."))
	return {"needs_phone": True, "email": email, "name": name}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def google_finish(ticket: str, full_name: str, phone: str):
	pending = _cache().get_value(f"cbc_google_new:{ticket}")
	_cache().delete_value(f"cbc_google_new:{ticket}")
	if not pending:
		return _page(_("That page expired"), _("Go back to the app and start Google sign-in again."))
	try:
		result = auth.provision_parent(
			(full_name or pending["name"]).strip(),
			pending["email"],
			common.normalize_phone(phone),
			secrets.token_urlsafe(24),
			pending["device"],
			ignore_policy=True,
		)
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		return _page(_("Check the details"), escape_html(str(e)))
	return _open_app(result, _("Your free trial has started. Open the app to add a child."))


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=8, seconds=15 * 60)
def exchange(code: str) -> dict:
	"""The app turns the one-time code from the browser into a device session."""
	key = f"cbc_handoff:{code or ''}"
	result = _cache().get_value(key)
	_cache().delete_value(key)
	if not result or not result.get("token"):
		raise frappe.AuthenticationError(_("That sign-in has expired. Start again."))
	return result
