"""A curriculum CSV builds strands, sub-strands and outcomes once, in the order of the file."""

import unittest

import frappe

from cbc_ai_tutor.setup.curriculum import import_text

GRADE = "CURRTEST 4"
CSV = f"""grade,learning_area,strand,sub_strand,outcome,competency
{GRADE},Mathematics,Numbers,Whole Numbers,read numbers up to 10000,Critical thinking
{GRADE},Mathematics,Numbers,Whole Numbers,identify place value,
{GRADE},Mathematics,Numbers,Fractions,identify fractions as part of a whole,
{GRADE},Mathematics,Measurement,Length,,
"""


class TestCurriculumImport(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Program", "program_name": GRADE, "program_abbreviation": "CT"}).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_the_file_creates_the_course_strands_sub_strands_and_outcomes(self):
		added = import_text(CSV)
		self.assertEqual(added, {"Course": 1, "Strand": 2, "Sub-strand": 3, "Learning Outcome": 3})
		self.assertTrue(
			frappe.db.exists("Program Course", {"parent": GRADE, "course": f"{GRADE} Mathematics"})
		)

	def test_importing_the_same_file_again_adds_nothing(self):
		import_text(CSV)
		self.assertEqual(import_text(CSV), {"Course": 0, "Strand": 0, "Sub-strand": 0, "Learning Outcome": 0})

	def test_items_are_ordered_as_they_appear_in_the_file(self):
		import_text(CSV)
		strands = frappe.get_all(
			"Strand", filters={"subject": f"{GRADE} Mathematics"}, fields=["strand_name", "order"]
		)
		self.assertEqual(
			sorted((s.order, s.strand_name) for s in strands), [(1, "Numbers"), (2, "Measurement")]
		)
		numbers = frappe.db.get_value("Strand", {"subject": f"{GRADE} Mathematics", "strand_name": "Numbers"})
		fractions = frappe.db.get_value("Sub-strand", {"strand": numbers, "name1": "Fractions"}, "order")
		self.assertEqual(fractions, 2)

	def test_a_row_for_a_grade_that_does_not_exist_is_refused_with_its_name(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Grade 99 does not exist"):
			import_text("grade,learning_area,strand,sub_strand\nGrade 99,Maths,Numbers,Counting\n")

	def test_a_row_missing_its_strand_names_the_row_and_column(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Row 2 has no strand"):
			import_text(f"grade,learning_area,strand,sub_strand\n{GRADE},Maths,,Counting\n")
