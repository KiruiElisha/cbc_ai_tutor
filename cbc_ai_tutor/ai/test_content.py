"""One AI call writes a sub-strand's lesson and quiz, saved as a draft for a teacher to check."""

import json
import unittest
from unittest.mock import patch

import frappe

from cbc_ai_tutor.ai import content

REPLY = {
	"title": "Fractions as equal parts",
	"summary": "A fraction is a part of a whole.",
	"body": "## Sharing a chapati\n\n" + "When Mama cuts a chapati into four equal pieces, each piece is one quarter. " * 6,
	"key_vocabulary": ["fraction", "numerator", "denominator"],
	"activities": "Fold a paper into 4 equal parts.",
	"reflection": "Where do you share things equally at home?",
	"minutes": 25,
	"quiz": [
		{"question": "What is one of four equal parts?", "options": ["1/4", "1/2", "4", "3/4"], "answer": 0},
		{"question": "In 3/5 the denominator is", "options": ["3", "5", "8", "2"], "answer": 1},
		{"question": "Which is bigger?", "options": ["1/2", "1/4", "1/8", "1/10"], "answer": 0},
		{"question": "Broken row with two options", "options": ["a", "b"], "answer": 0},
	],
}


class TestWriteLesson(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Course", "CONTENTTEST Grade 4 Mathematics"):
			frappe.get_doc({"doctype": "Course", "course_name": "CONTENTTEST Grade 4 Mathematics"}).insert()
		program = frappe.get_doc(
			{"doctype": "Program", "program_name": "CONTENTTEST Grade 4", "program_abbreviation": "CT4"}
		)
		program.append("courses", {"course": "CONTENTTEST Grade 4 Mathematics"})
		program.insert()
		self.strand = frappe.get_doc(
			{"doctype": "Strand", "strand_name": "Numbers", "subject": "CONTENTTEST Grade 4 Mathematics", "order": 1}
		).insert()
		self.sub = frappe.get_doc(
			{"doctype": "Sub-strand", "name1": "Fractions", "strand": self.strand.name, "order": 2}
		).insert()
		frappe.db.set_single_value("CBC Settings", "ai_lessons_publish", 0)

	def tearDown(self):
		frappe.db.rollback()

	def _write(self, reply=REPLY):
		answer = {"text": json.dumps(reply), "provider": "test", "model": "", "input_tokens": 0, "output_tokens": 0}
		with patch("cbc_ai_tutor.ai.providers.complete", return_value=answer) as call:
			name = content.write_lesson(self.sub.name)
		return frappe.get_doc("Lesson", name), call

	def test_the_lesson_lands_in_its_grade_sub_strand_as_a_draft(self):
		lesson, call = self._write()
		self.assertEqual(
			(lesson.program, lesson.course, lesson.sub_strand, lesson.published, lesson.lesson_order),
			("CONTENTTEST Grade 4", "CONTENTTEST Grade 4 Mathematics", self.sub.name, 0, 20),
		)
		self.assertIn("Grade 4", call.call_args.args[1][0]["content"])
		self.assertEqual(lesson.key_vocabulary, "fraction, numerator, denominator")

	def test_the_quiz_keeps_only_well_formed_questions_with_one_right_answer(self):
		lesson, _call = self._write()
		quiz = frappe.get_doc("Quiz", lesson.quiz)
		self.assertEqual(len(quiz.question), 3)
		first = frappe.get_doc("Question", quiz.question[0].question_link)
		self.assertEqual([o.is_correct for o in first.options], [1, 0, 0, 0])

	def test_a_sub_strand_with_a_lesson_is_not_written_again(self):
		self.assertIn(self.sub.name, content.without_lessons(1000))
		self._write()
		self.assertNotIn(self.sub.name, content.without_lessons(1000))

	def test_a_lesson_that_comes_back_too_short_is_refused(self):
		from cbc_ai_tutor.ai.providers import AIUnavailable

		with self.assertRaises(AIUnavailable):
			self._write({**REPLY, "body": "Too short."})
