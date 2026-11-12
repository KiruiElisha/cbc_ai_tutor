"""The lessons shipped with the app land on their topic, published and free, once."""

import json
import unittest

import frappe

from cbc_ai_tutor.setup.curriculum import import_text
from cbc_ai_tutor.setup.lessons import BUNDLED, add_lesson

GRADE = "LESSONTEST 7"


class TestBundledLessons(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Program", "program_name": GRADE, "program_abbreviation": "LT7"}).insert()
		self.row = next(r for r in json.loads((BUNDLED / "grade-7.json").read_text()) if r["learning_area"] == "Mathematics")
		import_text(
			"grade,learning_area,strand,sub_strand,outcome\n"
			f'{GRADE},Mathematics,"{self.row["strand"]}","{self.row["sub_strand"]}",Read big numbers\n'
		)

	def tearDown(self):
		frappe.db.rollback()

	def test_a_bundled_lesson_is_published_free_with_its_quiz_once(self):
		name = add_lesson(GRADE, self.row)
		lesson = frappe.get_doc("Lesson", name)
		self.assertEqual((lesson.published, lesson.is_free, lesson.course), (1, 1, f"{GRADE} Mathematics"))
		self.assertIn("<table", lesson.body)
		self.assertEqual(len(frappe.get_doc("Quiz", lesson.quiz).question), 4)
		self.assertIsNone(add_lesson(GRADE, self.row))

	def test_every_bundled_lesson_is_complete(self):
		for file in sorted(BUNDLED.glob("*.json")):
			for row in json.loads(file.read_text()):
				where = f"{file.name}: {row.get('title')}"
				for key in ("learning_area", "strand", "sub_strand", "title", "summary", "body"):
					self.assertTrue(row.get(key), where)
				self.assertGreaterEqual(len(row["quiz"]), 3, where)
				for q in row["quiz"]:
					self.assertEqual(len(set(q["options"])), 4, where)
					self.assertIn(q["answer"], range(4), where)
