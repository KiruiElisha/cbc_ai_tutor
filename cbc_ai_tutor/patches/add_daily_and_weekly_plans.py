"""Daily and Weekly plans beside Monthly, Termly and Yearly, for families who pay a little at a time.

Only plans the site does not have yet are added, with placeholder prices to set in Desk.
"""

import frappe

from cbc_ai_tutor.setup.install import PLANS


def execute():
	if not frappe.db.count("Subscription Plan"):
		return  # a new site gets every plan from seed_plans
	for plan in PLANS:
		if plan["billing_period"] in ("Daily", "Weekly") and not frappe.db.exists(
			"Subscription Plan", plan["plan_name"]
		):
			frappe.get_doc({"doctype": "Subscription Plan", "enabled": 1, **plan}).insert(
				ignore_permissions=True
			)
