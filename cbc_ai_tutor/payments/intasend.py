"""IntaSend M-Pesa STK push.

One host serves sandbox and live; the secret key's ``_test_`` / ``_live_`` prefix
picks the environment. A payment is an *invoice* whose ``state`` moves through
PENDING → PROCESSING → COMPLETE (or FAILED / CANCELED). Webhooks are not trusted on
their own: every one is confirmed by asking IntaSend for the invoice.
"""

from __future__ import annotations

import frappe
import requests
from frappe import _
from frappe.utils import cint

from cbc_ai_tutor.api import common

TIMEOUT = 30
PAID = "COMPLETE"
FAILED = {"FAILED", "CANCELED", "CANCELLED"}

FAILURE_MESSAGES = {
	"1032": "The M-Pesa prompt was cancelled.",
	"1037": "The phone could not be reached. Check it is on and has network, then try again.",
	"1": "There was not enough money in M-Pesa.",
	"2001": "The M-Pesa PIN was wrong.",
}


class IntaSendError(frappe.ValidationError):
	pass


def _base() -> str:
	return (common.setting("intasend_base_url") or "https://api.intasend.com").rstrip("/")


def _headers() -> dict:
	key = common.secret("intasend_secret_key")
	if not key:
		raise IntaSendError(_("M-Pesa payments are not set up yet."))
	return {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}


def enabled() -> bool:
	return bool(cint(common.setting("intasend_enabled", 0)) and common.secret("intasend_secret_key"))


def stk_push(amount: float, phone: str, api_ref: str, email: str | None = None) -> dict:
	body = {"amount": int(round(amount)), "phone_number": phone, "api_ref": api_ref}
	if email:
		body["email"] = email
	try:
		response = requests.post(
			f"{_base()}/api/v1/payment/mpesa-stk-push/", json=body, headers=_headers(), timeout=TIMEOUT
		)
	except requests.RequestException:
		frappe.log_error(title="IntaSend STK push unreachable", message=frappe.get_traceback())
		raise IntaSendError(_("M-Pesa could not be reached. Try again."))
	data = _json(response)
	if not response.ok:
		frappe.log_error(title=f"IntaSend STK push {response.status_code}", message=response.text[:2000])
		raise IntaSendError(_detail(data) or _("M-Pesa did not accept the request. Check the number and try again."))
	invoice = data.get("invoice") or {}
	if not invoice.get("invoice_id"):
		frappe.log_error(title="IntaSend STK push without invoice", message=response.text[:2000])
		raise IntaSendError(_("M-Pesa did not start the payment. Try again."))
	return data


def invoice_status(invoice_id: str) -> dict:
	try:
		response = requests.post(
			f"{_base()}/api/v1/payment/status/",
			json={"invoice_id": invoice_id},
			headers=_headers(),
			timeout=TIMEOUT,
		)
	except requests.RequestException:
		raise IntaSendError(_("M-Pesa could not be reached to check the payment."))
	data = _json(response)
	if not response.ok:
		frappe.log_error(title=f"IntaSend status {response.status_code}", message=response.text[:2000])
		raise IntaSendError(_("Could not check the M-Pesa payment."))
	return data.get("invoice") or data


def failure_text(invoice: dict) -> str:
	code = str(invoice.get("failed_code") or "")
	return _(FAILURE_MESSAGES.get(code) or invoice.get("failed_reason") or "The M-Pesa payment did not go through.")


def _json(response) -> dict:
	try:
		data = response.json()
	except ValueError:
		return {}
	return data if isinstance(data, dict) else {"errors": data}


def _detail(data: dict) -> str | None:
	errors = data.get("errors") or data.get("detail") or data.get("error")
	if isinstance(errors, list) and errors:
		first = errors[0]
		return first.get("detail") if isinstance(first, dict) else str(first)
	if isinstance(errors, str):
		return errors
	return None
