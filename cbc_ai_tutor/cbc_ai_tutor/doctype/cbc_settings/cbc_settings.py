# Copyright (c) 2026, ronoh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CBCSettings(Document):
	def validate(self):
		base = frappe.utils.get_url()
		self.intasend_webhook_url = f"{base}/api/method/cbc_ai_tutor.api.payments.intasend_webhook"
		self.paypal_webhook_url = f"{base}/api/method/cbc_ai_tutor.api.payments.paypal_webhook"
		self.paypal_return_url = f"{base}/api/method/cbc_ai_tutor.api.payments.paypal_return"
		if (self.trial_days or 0) < 0:
			self.trial_days = 0
		if self.ai_provider == "OpenAI Compatible" and self.ai_enabled and not self.ai_base_url:
			frappe.throw(_("An OpenAI Compatible provider needs its base URL."))
