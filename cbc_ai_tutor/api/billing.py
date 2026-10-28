"""Parent subscriptions, paid with M-Pesa (IntaSend) or PayPal.

Payment is one-off per period: paying a plan adds its days to whatever access the
family already has, so renewing early never loses days. ``fulfil`` is the only
place access is granted. It locks the transaction row and checks the amount and
currency the gateway reports against the plan, so a duplicate webhook, a poll and
the PayPal return page arriving together still grant access once.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_days, cint, flt, get_datetime, get_url, now_datetime, time_diff_in_seconds

from cbc_ai_tutor.api import common
from cbc_ai_tutor.payments import intasend, paypal

TX = "Payment Transaction"
RECHECK_SECONDS = 8


def _plan_card(plan) -> dict:
	return {
		"name": plan.name,
		"plan_name": plan.plan_name,
		"billing_period": plan.billing_period,
		"duration_days": plan.duration_days,
		"price_kes": flt(plan.price_kes),
		"price_paypal": flt(plan.price_paypal),
		"paypal_currency": paypal.currency(),
		"max_learners": cint(plan.max_learners),
		"ai_messages_per_day": cint(plan.ai_messages_per_day),
		"tagline": plan.tagline,
		"features": [line.strip() for line in (plan.features or "").splitlines() if line.strip()],
	}


@frappe.whitelist()
def plans() -> dict:
	common.require_login()
	rows = frappe.get_all(
		"Subscription Plan",
		filters={"enabled": 1},
		fields=["*"],
		order_by="display_order asc, price_kes asc",
	)
	return {
		"plans": [_plan_card(r) for r in rows],
		"gateways": {"mpesa": intasend.enabled(), "paypal": paypal.enabled()},
	}


@frappe.whitelist()
def subscription() -> dict:
	guardian = common.current_parent()
	sub = common.subscription_for(guardian)
	state = common.subscription_state(sub)
	children = common.children_of(guardian)
	pending = frappe.get_all(
		TX,
		filters={"guardian": guardian, "status": "Pending"},
		fields=["name", "gateway", "plan", "amount", "currency", "creation"],
		order_by="creation desc",
		limit_page_length=3,
	)
	history = frappe.get_all(
		TX,
		filters={"guardian": guardian, "status": ["in", ["Completed", "Failed", "Cancelled"]]},
		fields=["name", "gateway", "plan", "amount", "currency", "status", "receipt_number", "completed_on", "creation", "failure_reason"],
		order_by="creation desc",
		limit_page_length=20,
	)
	return {
		"active": 1 if state.active else 0,
		"status": state.status,
		"plan": state.plan,
		"until": str(state.until) if state.until else None,
		"max_learners": state.max_learners,
		"learners": len(children),
		"ai_messages_per_day": state.ai_messages_per_day,
		"pending": [_stringify(p) for p in pending],
		"history": [_stringify(h) for h in history],
	}


def _stringify(row):
	return {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()}


def _enabled_plan(plan: str):
	doc = frappe.get_doc("Subscription Plan", plan)
	if not doc.enabled:
		frappe.throw(_("That plan is no longer offered."))
	return doc


def _check_capacity(guardian: str, plan) -> None:
	children = frappe.db.count("Student", {"name": ["in", common.children_of(guardian) or [""]], "enabled": 1})
	if children > cint(plan.max_learners):
		frappe.throw(
			_("You have {0} learners and {1} covers {2}. Pick a bigger plan or switch a learner off first.").format(
				children, plan.plan_name, plan.max_learners
			)
		)


def _new_tx(guardian: str, plan, gateway: str, amount: float, currency: str, phone: str | None = None):
	tx = frappe.get_doc(
		{
			"doctype": TX,
			"guardian": guardian,
			"user": frappe.session.user,
			"plan": plan.name,
			"gateway": gateway,
			"status": "Pending",
			"amount": amount,
			"currency": currency,
			"phone": phone,
		}
	)
	tx.insert(ignore_permissions=True)
	return tx


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=6, seconds=10 * 60)
def pay_mpesa(plan: str, phone: str) -> dict:
	"""Send an M-Pesa prompt to the parent's phone."""
	guardian = common.current_parent()
	if not intasend.enabled():
		frappe.throw(_("M-Pesa payments are not available right now."))
	plan_doc = _enabled_plan(plan)
	_check_capacity(guardian, plan_doc)
	phone = common.normalize_phone(phone)

	tx = _new_tx(guardian, plan_doc, "IntaSend M-Pesa", flt(plan_doc.price_kes), "KES", phone)
	frappe.db.commit()
	try:
		data = intasend.stk_push(flt(plan_doc.price_kes), phone, tx.name, frappe.db.get_value("User", frappe.session.user, "email"))
	except intasend.IntaSendError as e:
		tx.db_set({"status": "Failed", "failure_reason": str(e)})
		frappe.db.commit()
		raise
	invoice = data.get("invoice") or {}
	tx.db_set(
		{
			"gateway_reference": invoice.get("invoice_id"),
			"gateway_response": json.dumps(data, default=str)[:60000],
			"last_checked_on": now_datetime(),
		}
	)
	return {
		"transaction": tx.name,
		"status": "Pending",
		"message": _("Check your phone and enter your M-Pesa PIN to pay KES {0}.").format(int(flt(plan_doc.price_kes))),
	}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=6, seconds=10 * 60)
def pay_paypal(plan: str) -> dict:
	"""A PayPal order. The app opens ``approve_url`` in the browser."""
	guardian = common.current_parent()
	if not paypal.enabled():
		frappe.throw(_("PayPal payments are not available right now."))
	plan_doc = _enabled_plan(plan)
	_check_capacity(guardian, plan_doc)
	if flt(plan_doc.price_paypal) <= 0:
		frappe.throw(_("This plan has no PayPal price yet. Use M-Pesa."))

	tx = _new_tx(guardian, plan_doc, "PayPal", flt(plan_doc.price_paypal), paypal.currency())
	frappe.db.commit()
	base = get_url()
	return_url = f"{base}/api/method/cbc_ai_tutor.api.payments.paypal_return?tx={tx.name}"
	cancel_url = f"{base}/api/method/cbc_ai_tutor.api.payments.paypal_cancel?tx={tx.name}"
	try:
		order = paypal.create_order(
			tx.name,
			flt(plan_doc.price_paypal),
			f"{common.setting('app_name') or 'CBC AI Tutor'} {plan_doc.plan_name}",
			return_url,
			cancel_url,
		)
	except paypal.PayPalError as e:
		tx.db_set({"status": "Failed", "failure_reason": str(e)})
		frappe.db.commit()
		raise
	link = paypal.approve_link(order)
	if not link:
		tx.db_set({"status": "Failed", "failure_reason": "PayPal returned no approval link"})
		frappe.db.commit()
		frappe.throw(_("PayPal could not start the payment. Try again."))
	tx.db_set(
		{
			"gateway_reference": order.get("id"),
			"gateway_response": json.dumps(order, default=str)[:60000],
			"last_checked_on": now_datetime(),
		}
	)
	return {"transaction": tx.name, "status": "Pending", "approve_url": link}


@frappe.whitelist()
def transaction(name: str) -> dict:
	"""Where a payment stands. Asks the gateway when the answer may have changed."""
	guardian = common.current_parent()
	tx = frappe.get_doc(TX, name)
	if tx.guardian != guardian:
		raise frappe.PermissionError(_("That payment is not yours."))
	if tx.status == "Pending" and (
		not tx.last_checked_on or time_diff_in_seconds(now_datetime(), tx.last_checked_on) >= RECHECK_SECONDS
	):
		reconcile(tx.name)
		frappe.db.commit()
		tx.reload()
	return {
		"transaction": tx.name,
		"status": tx.status,
		"gateway": tx.gateway,
		"amount": tx.amount,
		"currency": tx.currency,
		"receipt_number": tx.receipt_number,
		"failure_reason": tx.failure_reason,
		"subscription": subscription() if tx.status == "Completed" else None,
	}


@frappe.whitelist(methods=["POST"])
def cancel_pending(name: str) -> dict:
	"""The parent gave up on a payment. A late success still counts."""
	guardian = common.current_parent()
	tx = frappe.get_doc(TX, name)
	if tx.guardian != guardian:
		raise frappe.PermissionError(_("That payment is not yours."))
	reconcile(tx.name)
	tx.reload()
	if tx.status == "Pending":
		tx.db_set({"status": "Cancelled", "failure_reason": _("Cancelled in the app.")})
	return {"transaction": tx.name, "status": tx.status}


# ---------------------------------------------------------------------------
# Gateway truth
# ---------------------------------------------------------------------------


def reconcile(name: str) -> str:
	"""Ask the gateway about one transaction and act on the answer."""
	tx = frappe.db.get_value(TX, name, ["name", "gateway", "gateway_reference", "status"], as_dict=True)
	if not tx or tx.status not in ("Pending", "Cancelled") or not tx.gateway_reference:
		return tx.status if tx else "Missing"
	frappe.db.set_value(TX, name, "last_checked_on", now_datetime(), update_modified=False)
	try:
		if tx.gateway == "IntaSend M-Pesa":
			apply_intasend_invoice(intasend.invoice_status(tx.gateway_reference), expected_tx=name)
		else:
			order = paypal.get_order(tx.gateway_reference)
			if order.get("status") == "APPROVED":
				order = paypal.capture(tx.gateway_reference)
			apply_paypal_order(order, expected_tx=name)
	except (intasend.IntaSendError, paypal.PayPalError):
		frappe.clear_messages()
	return frappe.db.get_value(TX, name, "status")


def apply_intasend_invoice(invoice: dict, expected_tx: str | None = None) -> str | None:
	invoice_id = invoice.get("invoice_id")
	name = frappe.db.get_value(TX, {"gateway": "IntaSend M-Pesa", "gateway_reference": invoice_id}, "name")
	if not name and invoice_id and invoice.get("api_ref"):
		# The webhook can beat the request that stores the invoice id.
		name = frappe.db.get_value(
			TX,
			{"name": invoice["api_ref"], "gateway": "IntaSend M-Pesa", "gateway_reference": ("is", "not set")},
			"name",
		)
		if name:
			frappe.db.set_value(TX, name, "gateway_reference", invoice_id, update_modified=False)
	if not name or (expected_tx and name != expected_tx):
		return None
	state = (invoice.get("state") or "").upper()
	payload = json.dumps(invoice, default=str)[:60000]
	if state == intasend.PAID:
		fulfil(
			name,
			amount=flt(invoice.get("value")),
			currency=(invoice.get("currency") or "KES").upper(),
			reference=invoice.get("api_ref"),
			receipt=invoice.get("mpesa_reference") or invoice.get("provider_ref"),
			raw=payload,
		)
	elif state in intasend.FAILED:
		_fail(name, intasend.failure_text(invoice), payload)
	else:
		frappe.db.set_value(TX, name, "gateway_response", payload, update_modified=False)
	return name


def apply_paypal_order(order: dict, expected_tx: str | None = None) -> str | None:
	name = frappe.db.get_value(TX, {"gateway": "PayPal", "gateway_reference": order.get("id")}, "name")
	if not name or (expected_tx and name != expected_tx):
		return None
	payload = json.dumps(order, default=str)[:60000]
	cap = paypal.completed_capture(order)
	if cap:
		fulfil(name, amount=cap["amount"], currency=(cap["currency"] or "").upper(), reference=cap["reference"], receipt=cap["id"], raw=payload)
	elif order.get("status") == "VOIDED":
		_fail(name, _("The PayPal payment was voided."), payload)
	else:
		frappe.db.set_value(TX, name, "gateway_response", payload, update_modified=False)
	return name


def _fail(name: str, reason: str, raw: str | None = None):
	row = frappe.db.sql(f"select status from `tab{TX}` where name=%s for update", name, as_dict=True)
	if not row or row[0].status == "Completed":
		return
	values = {"status": "Failed", "failure_reason": reason}
	if raw:
		values["gateway_response"] = raw
	frappe.db.set_value(TX, name, values)


def fulfil(name: str, amount: float, currency: str, reference: str | None, receipt: str | None, raw: str | None = None) -> bool:
	"""Grant the plan's days. Safe to call any number of times."""
	row = frappe.db.sql(
		f"select name, status, amount, currency, plan, guardian, user from `tab{TX}` where name=%s for update",
		name,
		as_dict=True,
	)
	if not row:
		return False
	tx = row[0]
	if tx.status == "Completed":
		return False

	problems = []
	if reference and reference != tx.name:
		problems.append(f"reference {reference} does not match {tx.name}")
	if (currency or "").upper() != (tx.currency or "").upper():
		problems.append(f"currency {currency} instead of {tx.currency}")
	if flt(amount) + 0.005 < flt(tx.amount):
		problems.append(f"paid {amount} of {tx.amount}")
	if problems:
		frappe.db.set_value(
			TX,
			name,
			{"failure_reason": "Not applied: " + "; ".join(problems), "gateway_response": raw or ""},
		)
		frappe.log_error(title=f"Payment {name} did not match its plan", message="; ".join(problems))
		return False

	plan = frappe.get_doc("Subscription Plan", tx.plan)
	sub_name = frappe.db.get_value("Parent Subscription", {"guardian": tx.guardian}, "name")
	sub = frappe.get_doc("Parent Subscription", sub_name) if sub_name else frappe.get_doc(
		{"doctype": "Parent Subscription", "guardian": tx.guardian, "user": tx.user}
	)
	now = now_datetime()
	starts_from = now
	for value in (sub.current_period_end if sub.status == "Active" else None, sub.trial_ends_on if sub.status == "Trial" else None):
		if value and get_datetime(value) > starts_from:
			starts_from = get_datetime(value)
	if sub.status != "Active" or not sub.current_period_start:
		sub.current_period_start = now
	sub.status = "Active"
	sub.plan = plan.name
	sub.current_period_end = add_days(starts_from, cint(plan.duration_days))
	sub.max_learners = cint(plan.max_learners)
	sub.ai_messages_per_day = cint(plan.ai_messages_per_day)
	sub.last_payment = tx.name
	sub.reminder_sent_on = None
	sub.flags.ignore_permissions = True
	sub.save()

	values = {
		"status": "Completed",
		"completed_on": now,
		"receipt_number": (receipt or "")[:140],
		"subscription": sub.name,
		"failure_reason": None,
	}
	if raw:
		values["gateway_response"] = raw
	frappe.db.set_value(TX, name, values)
	_notify_paid(tx, plan, sub)
	return True


def _notify_paid(tx, plan, sub):
	email = frappe.db.get_value("User", tx.user, "email") if tx.user else None
	if not email:
		return
	app = common.setting("app_name") or "CBC AI Tutor"
	common.notify(
		[email],
		_("{0}: payment received").format(app),
		_(
			"<p>Thank you. We received {0} {1} for the {2} plan.</p>"
			"<p>Your family's access now runs until <b>{3}</b>.</p>"
			"<p>Reference: {4}</p>"
		).format(tx.currency, frappe.utils.fmt_money(tx.amount), plan.plan_name, frappe.utils.format_datetime(sub.current_period_end), tx.name),
	)
