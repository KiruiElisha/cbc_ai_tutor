"""Keep a Program Enrollment for the learner's current grade.

Replaces the "Student Enrollment" server script, which used the calendar year as
the academic year (the Academic Year record often did not exist) and refused to
save learners without a grade.
"""

import frappe
from frappe.utils import getdate, nowdate

from cbc_ai_tutor.api import common


def academic_year(on=None) -> str:
	"""The Kenyan school year runs January to December; create it the first time it is needed."""
	year = getdate(on or nowdate()).year
	name = str(year)
	existing = frappe.db.get_value(
		"Academic Year",
		{"year_start_date": ("<=", f"{year}-06-30"), "year_end_date": (">=", f"{year}-06-30")},
		"name",
	)
	if existing:
		return existing
	if not frappe.db.exists("Academic Year", name):
		frappe.get_doc(
			{
				"doctype": "Academic Year",
				"academic_year_name": name,
				"year_start_date": f"{year}-01-01",
				"year_end_date": f"{year}-12-31",
			}
		).insert(ignore_permissions=True)
	return name


def enroll(doc, method=None):
	if doc.get("custom_grade") and doc.enabled:
		_enroll(doc)


def enroll_on_grade_change(doc, method=None):
	before = doc.get_doc_before_save()
	if before and before.get("custom_grade") != doc.get("custom_grade"):
		enroll(doc)


def _enroll(doc):
	year = academic_year()
	if frappe.db.exists(
		"Program Enrollment",
		{"student": doc.name, "program": doc.custom_grade, "academic_year": year, "docstatus": ("<", 2)},
	):
		return

	frappe.db.savepoint("cbc_enroll")
	try:
		with common.as_administrator():
			enrollment = frappe.get_doc(
				{
					"doctype": "Program Enrollment",
					"student": doc.name,
					"student_name": doc.student_name,
					"program": doc.custom_grade,
					"academic_year": year,
					"enrollment_date": doc.joining_date or nowdate(),
				}
			)
			enrollment.insert(ignore_permissions=True)
			enrollment.submit()
	except Exception:
		# A learner must still be saved when the Education set-up is incomplete;
		# the app reads the grade from the Student record, not the enrollment.
		frappe.db.rollback(save_point="cbc_enroll")
		frappe.log_error(title=f"Could not enroll {doc.name} in {doc.custom_grade}")
