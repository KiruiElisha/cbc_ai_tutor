"""One AI call writes a sub-strand's lesson and quiz, saved as a draft for a teacher to check."""

import json
import unittest
from unittest.mock import patch

import frappe

from cbc_ai_tutor.ai import content

REPLY = {
	"title": "Fractions as equal parts",
	"summary": "A fraction is a part of a whole.",
	"body": "## Sharing a chapati\n\n"
	+ "When Mama cuts a chapati into four equal pieces, each piece is one quarter. " * 6,
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
			{
				"doctype": "Strand",
				"strand_name": "Numbers",
				"subject": "CONTENTTEST Grade 4 Mathematics",
				"order": 1,
			}
		).insert()
		self.sub = frappe.get_doc(
			{"doctype": "Sub-strand", "name1": "Fractions", "strand": self.strand.name, "order": 2}
		).insert()
		frappe.db.set_single_value("CBC Settings", "ai_lessons_publish", 0)

	def tearDown(self):
		frappe.db.rollback()

	def _write(self, reply=REPLY):
		answer = {
			"text": json.dumps(reply),
			"provider": "test",
			"model": "",
			"input_tokens": 0,
			"output_tokens": 0,
		}
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

	def test_a_reply_that_is_not_json_is_asked_for_once_more(self):
		broken = {"text": '{"title": "Fractions", "body": "cut off', "provider": "test", "model": ""}
		good = {"text": json.dumps(REPLY), "provider": "test", "model": ""}
		with patch("cbc_ai_tutor.ai.providers.complete", side_effect=[broken, good]) as call:
			name = content.write_lesson(self.sub.name)
		self.assertEqual(frappe.db.get_value("Lesson", name, "sub_strand"), self.sub.name)
		self.assertEqual(call.call_count, 2)
		self.assertIn("not valid JSON", call.call_args.args[1][0]["content"])

	def test_a_second_unreadable_reply_gives_up(self):
		from cbc_ai_tutor.ai.providers import AIBadReply

		broken = {"text": "Sorry, here is the lesson: Fractions", "provider": "test", "model": ""}
		with patch("cbc_ai_tutor.ai.providers.complete", return_value=broken) as call:
			with self.assertRaises(AIBadReply):
				content.write_lesson(self.sub.name)
		self.assertEqual(call.call_count, 2)

	def test_writing_one_grade_only_picks_that_grades_sub_strands(self):
		self.assertIn(self.sub.name, content.without_lessons(1000, "CONTENTTEST Grade 4"))
		frappe.get_doc(
			{"doctype": "Program", "program_name": "CONTENTTEST Grade 5", "program_abbreviation": "CT5"}
		).insert()
		self.assertNotIn(self.sub.name, content.without_lessons(1000, "CONTENTTEST Grade 5"))


class TestFreeLessonRun(unittest.TestCase):
	"""The daily run: a slow lesson is skipped, a topic is never written twice, a dead provider stops it."""

	def _run(self, missing, write, existing=()):
		written = []

		def fake_write(sub_strand):
			written.append(sub_strand)
			return write(sub_strand)

		with (
			patch.object(content, "free_lessons_missing", side_effect=[missing, []]),
			patch.object(content, "write_lesson", side_effect=fake_write),
			patch.object(content.frappe.db, "exists", side_effect=lambda dt, f: f["sub_strand"] in existing),
			patch.object(content.frappe.db, "set_value"),
			patch.object(content.frappe.db, "commit"),
			patch.object(content.frappe.db, "rollback"),
			patch.object(content.frappe, "log_error"),
		):
			result = content.write_free()
		return written, result

	def test_one_lesson_that_times_out_does_not_stop_the_rest(self):
		def write(sub):
			if sub == "SS-1":
				raise content.providers.AIUnavailable("The tutor took too long to answer. Try again.")
			return "L-" + sub

		written, result = self._run([("SS-1", None, "Grade 9"), ("SS-2", None, "Grade 9")], write)
		self.assertEqual(written, ["SS-1", "SS-2"])
		self.assertEqual(result["written"], 1)

	def test_a_topic_that_got_a_lesson_meanwhile_is_not_written_again(self):
		written, _ = self._run(
			[("SS-1", None, "Grade 9"), ("SS-2", None, "Grade 9")], lambda sub: "L-" + sub, existing={"SS-1"}
		)
		self.assertEqual(written, ["SS-2"])

	def test_a_provider_that_keeps_failing_stops_the_run(self):
		def down(sub):
			raise content.providers.AIUnavailable("The tutor can't be reached right now.")

		missing = [(f"SS-{n}", None, "Grade 9") for n in range(6)]
		written, _ = self._run(missing, down)
		self.assertEqual(len(written), content.FAILURES_IN_A_ROW)

	def test_a_rejected_key_stops_the_run_at_once(self):
		def rejected(sub):
			raise content.providers.AIUnavailable("The AI provider rejected the API key.")

		written, _ = self._run([("SS-1", None, "G"), ("SS-2", None, "G")], rejected)
		self.assertEqual(written, ["SS-1"])
