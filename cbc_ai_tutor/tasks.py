"""Scheduled jobs (see ``scheduler_events`` in hooks.py)."""

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, format_datetime, getdate, now_datetime, nowdate

from cbc_ai_tutor.api import billing, common

RENEWAL_NOTICE_DAYS = 3
SYNC_RECEIPT_DAYS = 120


def reconcile_pending_payments():
	"""Catch payments whose webhook never arrived and the app stopped polling for.

	Pending M-Pesa prompts expire within minutes; anything still pending after two
	days is given up on, so a forgotten prompt does not stay open forever.
	"""
	now = now_datetime()
	rows = frappe.get_all(
		billing.TX,
		filters={
			"status": "Pending",
			"creation": ["between", [add_days(now, -2), add_to_date(now, minutes=-2)]],
		},
		pluck="name",
		limit_page_length=200,
	)
	for name in rows:
		try:
			billing.reconcile(name)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Could not reconcile {name}")

	stale = frappe.get_all(
		billing.TX,
		filters={"status": "Pending", "creation": ["<", add_days(now, -2)]},
		pluck="name",
		limit_page_length=500,
	)
	for name in stale:
		frappe.db.set_value(
			billing.TX, name, {"status": "Failed", "failure_reason": _("The payment was not completed.")}
		)
	frappe.db.commit()


def expire_subscriptions():
	now = now_datetime()
	for status, field in (("Active", "current_period_end"), ("Trial", "trial_ends_on")):
		for name in frappe.get_all(
			"Parent Subscription", filters={"status": status, field: ["<", now]}, pluck="name"
		):
			frappe.db.set_value("Parent Subscription", name, "status", "Expired")
	frappe.db.commit()


def send_renewal_reminders():
	"""One email a few days before access runs out."""
	soon = add_days(now_datetime(), RENEWAL_NOTICE_DAYS)
	app = common.setting("app_name") or "CBC AI Tutor"
	rows = frappe.get_all(
		"Parent Subscription",
		filters={"status": ["in", ["Active", "Trial"]]},
		fields=["name", "user", "status", "current_period_end", "trial_ends_on", "reminder_sent_on"],
	)
	for row in rows:
		ends = row.current_period_end if row.status == "Active" else row.trial_ends_on
		if not ends or ends > soon or ends < now_datetime() or row.reminder_sent_on:
			continue
		email = frappe.db.get_value("User", row.user, "email") if row.user else None
		if email:
			common.notify(
				[email],
				_("{0}: access ends on {1}").format(app, format_datetime(ends, "d MMM")),
				_(
					"<p>Your family's {0} access ends on <b>{1}</b>.</p>"
					"<p>Renew in the app (Parent, then Subscription) with M-Pesa or PayPal. "
					"Paying early adds the new days on top, so you lose nothing.</p>"
				).format(app, format_datetime(ends)),
			)
		frappe.db.set_value("Parent Subscription", row.name, "reminder_sent_on", nowdate(), update_modified=False)
	frappe.db.commit()


def purge_device_sessions():
	frappe.db.delete("CBC Device Session", {"expires_on": ["<", add_days(now_datetime(), -30)]})
	frappe.db.delete("CBC Device Session", {"revoked": 1, "modified": ["<", add_days(now_datetime(), -30)]})
	frappe.db.commit()


def purge_sync_receipts():
	"""Receipts only need to outlive a device's offline queue."""
	frappe.db.delete("CBC Sync Receipt", {"creation": ["<", add_days(getdate(), -SYNC_RECEIPT_DAYS)]})
	frappe.db.commit()
