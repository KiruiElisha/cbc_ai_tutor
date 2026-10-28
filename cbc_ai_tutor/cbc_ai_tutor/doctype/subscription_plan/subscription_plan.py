# Copyright (c) 2026, ronoh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SubscriptionPlan(Document):
	def validate(self):
		if (self.duration_days or 0) <= 0:
			frappe.throw(_("A plan must give at least one day of access."))
		if (self.max_learners or 0) <= 0:
			frappe.throw(_("A plan must cover at least one learner."))
		if (self.price_kes or 0) <= 0:
			frappe.throw(_("Set the M-Pesa price in KES."))
