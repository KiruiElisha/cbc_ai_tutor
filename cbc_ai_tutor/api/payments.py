"""Public endpoints the payment gateways call. None of them trust the request alone."""

from __future__ import annotations

import hmac
import json

import frappe
from frappe import _
from frappe.utils import escape_html

from cbc_ai_tutor.api import billing, common
from cbc_ai_tutor.payments import intasend, paypal


def _body() -> dict:
	try:
		return json.loads(frappe.request.get_data(as_text=True) or "{}")
	except ValueError:
		return {}


def _ok(payload: dict | None = None):
	frappe.local.response.http_status_code = 200
	return payload or {"received": True}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def intasend_webhook():
	"""``collection_event``: check the challenge, then confirm with IntaSend before acting."""
	event = _body()
	challenge = common.secret("intasend_webhook_challenge")
	if not challenge or not hmac.compare_digest(str(event.get("challenge") or ""), challenge):
		frappe.local.response.http_status_code = 401
		return {"received": False}

	if event.get("topic") not in (None, "", "collection_event") or not event.get("invoice_id"):
		return _ok()
	try:
		frappe.set_user("Administrator")
		invoice = intasend.invoice_status(event["invoice_id"])
		billing.apply_intasend_invoice(invoice)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="IntaSend webhook could not be applied", message=frappe.get_traceback())
	finally:
		frappe.set_user("Guest")
	return _ok()


@frappe.whitelist(allow_guest=True, methods=["POST"])
def paypal_webhook():
	event = _body()
	try:
		verified = paypal.verify_webhook(frappe.request.headers, event)
	except paypal.PayPalError:
		verified = False
	if not verified:
		frappe.local.response.http_status_code = 401
		return {"received": False}

	kind = event.get("event_type")
	resource = event.get("resource") or {}
	order_id = None
	if kind == "CHECKOUT.ORDER.APPROVED":
		order_id = resource.get("id")
	elif kind in ("PAYMENT.CAPTURE.COMPLETED", "PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
		order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id")
	if not order_id:
		return _ok()
	try:
		frappe.set_user("Administrator")
		name = frappe.db.get_value("Payment Transaction", {"gateway": "PayPal", "gateway_reference": order_id}, "name")
		if name:
			billing.reconcile(name)
			if kind in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
				billing._fail(name, _("PayPal declined the payment."))
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="PayPal webhook could not be applied", message=frappe.get_traceback())
	finally:
		frappe.set_user("Guest")
	return _ok()


def _page(title: str, message: str, tx: str | None, ok: bool):
	app = escape_html(common.setting("app_name") or "CBC AI Tutor")
	deep_link = f"cbctutor://payment?tx={escape_html(tx or '')}"
	colour = "#15803d" if ok else "#b91c1c"
	html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{app}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f8fafc;margin:0;display:grid;place-items:center;min-height:100vh}}
.card{{background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(0,0,0,.1);padding:32px;max-width:420px;text-align:center}}
h1{{color:{colour};font-size:22px;margin:0 0 12px}}p{{color:#334155;line-height:1.5}}
a{{display:inline-block;margin-top:16px;background:#0f766e;color:#fff;padding:12px 20px;border-radius:10px;text-decoration:none;font-weight:600}}</style>
</head><body><div class="card"><h1>{escape_html(title)}</h1><p>{escape_html(message)}</p>
<a href="{deep_link}">Back to {app}</a></div></body></html>"""
	frappe.local.response["type"] = "download"
	frappe.local.response["content_type"] = "text/html; charset=utf-8"
	frappe.local.response["filename"] = "payment.html"
	frappe.local.response["filecontent"] = html.encode()
	frappe.local.response["display_content_as"] = "inline"


@frappe.whitelist(allow_guest=True, methods=["GET"])
def paypal_return(tx: str | None = None, token: str | None = None, **kwargs):
	"""PayPal sends the parent here after approving. Capture now; the webhook is the backstop."""
	status = None
	try:
		frappe.set_user("Administrator")
		name = frappe.db.get_value("Payment Transaction", {"name": tx, "gateway": "PayPal", "gateway_reference": token}, "name")
		if name:
			status = billing.reconcile(name)
			frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="PayPal return could not be applied", message=frappe.get_traceback())
	finally:
		frappe.set_user("Guest")

	if status == "Completed":
		_page(_("Payment received"), _("Thank you. Your family's access is open. You can go back to the app."), tx, True)
	elif status == "Failed":
		_page(_("Payment not completed"), _("PayPal did not complete the payment. Go back to the app to try again."), tx, False)
	else:
		_page(_("Payment is processing"), _("PayPal is still confirming the payment. The app will update in a moment."), tx, True)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def paypal_cancel(tx: str | None = None, token: str | None = None, **kwargs):
	try:
		frappe.set_user("Administrator")
		name = frappe.db.get_value("Payment Transaction", {"name": tx, "gateway": "PayPal", "gateway_reference": token}, "name")
		if name and frappe.db.get_value("Payment Transaction", name, "status") == "Pending":
			frappe.db.set_value("Payment Transaction", name, {"status": "Cancelled", "failure_reason": _("Cancelled on PayPal.")})
			frappe.db.commit()
	finally:
		frappe.set_user("Guest")
	_page(_("Payment cancelled"), _("No money was taken. Go back to the app to choose another way to pay."), tx, False)
