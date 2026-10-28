# Copyright (c) 2026, ronoh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Lesson(Document):
	def validate(self):
		if self.sub_strand and not self.strand:
			self.strand = frappe.db.get_value("Sub-strand", self.sub_strand, "strand")
		if self.learning_outcome and not self.sub_strand:
			self.sub_strand = frappe.db.get_value("Learning Outcome", self.learning_outcome, "sub_strand")
		if self.strand and self.course:
			subject = frappe.db.get_value("Strand", self.strand, "subject")
			if subject and subject != self.course:
				frappe.throw(_("Strand {0} belongs to {1}, not {2}.").format(self.strand, subject, self.course))
		if self.learning_outcome and self.sub_strand:
			owner = frappe.db.get_value("Learning Outcome", self.learning_outcome, "sub_strand")
			if owner and owner != self.sub_strand:
				frappe.throw(_("Learning outcome {0} belongs to sub-strand {1}.").format(self.learning_outcome, owner))
