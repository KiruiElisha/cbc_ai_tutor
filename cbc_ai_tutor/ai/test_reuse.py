"""A first question asked again gets the earlier answer, with no AI call and no daily limit used."""

import json
import unittest

import frappe
from frappe.utils import add_days, now_datetime

from cbc_ai_tutor.ai import reuse


class TestNormalize(unittest.TestCase):
	def test_greetings_punctuation_and_case_do_not_change_the_question(self):
		self.assertEqual(
			reuse.normalize("Hello Mwalimu! Please, what is EVAPORATION??"),
			reuse.normalize("what is evaporation"),
		)

	def test_a_question_too_short_to_match_safely_gets_no_key(self):
		self.assertIsNone(reuse.question_key("Grade 5", "L1", "why?"))
		self.assertEqual(
			reuse.question_key("Grade 5", "L1", "What happens to water when it evaporates?"),
			"Grade 5|L1|what happens to water when it evaporates",
		)

	def test_the_same_words_in_another_grade_or_lesson_are_a_different_question(self):
		q = "What happens to water when it evaporates?"
		self.assertNotEqual(reuse.question_key("Grade 5", "L1", q), reuse.question_key("Grade 6", "L1", q))
		self.assertNotEqual(reuse.question_key("Grade 5", "L1", q), reuse.question_key("Grade 5", "L2", q))


class TestSharedAnswers(unittest.TestCase):
	KEY = "Grade 5|REUSETEST|what happens to water when it evaporates"

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("CBC Settings", "ai_reuse_answers", 1)

	def tearDown(self):
		frappe.db.rollback()

	def _answer(self, html, *, source="AI", feedback=None, days_ago=0):
		doc = frappe.get_doc(
			{
				"doctype": "AI Tutor Interaction",
				"student": "REUSETEST-STUDENT",
				"date": now_datetime(),
				"question": "What happens to water when it evaporates?",
				"ai_response": html,
				"question_key": self.KEY,
				"source": source,
				"feedback": feedback,
			}
		).insert(ignore_permissions=True, ignore_links=True)
		if days_ago:
			frappe.db.set_value(
				doc.doctype, doc.name, "creation", add_days(now_datetime(), -days_ago), update_modified=False
			)
		return doc

	def test_an_earlier_ai_answer_to_the_same_question_is_reused(self):
		self._answer("<p>It turns into water vapour.</p>")
		self.assertEqual(reuse.cached_answer(self.KEY), "<p>It turns into water vapour.</p>")

	def test_an_answer_marked_unhelpful_or_too_old_is_not_reused(self):
		self._answer("<p>Wrong.</p>", feedback="Unhelpful")
		self._answer("<p>Old.</p>", days_ago=400)
		self.assertIsNone(reuse.cached_answer(self.KEY))

	def test_reuse_switched_off_always_asks_the_ai(self):
		self._answer("<p>It turns into water vapour.</p>")
		frappe.db.set_single_value("CBC Settings", "ai_reuse_answers", 0)
		self.assertIsNone(reuse.cached_answer(self.KEY))


class TestSharedPractice(unittest.TestCase):
	KEY = "Grade 5|REUSETEST-LESSON"

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("CBC Settings", "ai_reuse_answers", 1)

	def tearDown(self):
		frappe.db.rollback()

	def _set(self, student, texts):
		questions = [{"question": t, "options": ["a", "b", "c", "d"], "answer": 0, "explanation": ""} for t in texts]
		frappe.get_doc(
			{
				"doctype": "Practice Questions",
				"student": student,
				"questions": json.dumps(questions),
				"topic_key": self.KEY,
				"source": "AI",
			}
		).insert(ignore_permissions=True, ignore_links=True)

	def test_questions_written_for_a_topic_are_shared_preferring_unseen_ones(self):
		self._set("REUSETEST-A", ["Q1", "Q2", "Q3"])
		self._set("REUSETEST-B", ["Q4", "Q5", "Q6"])
		picked = reuse.pooled_practice(self.KEY, 3, "REUSETEST-A")
		self.assertEqual(sorted(q["question"] for q in picked), ["Q4", "Q5", "Q6"])

	def test_too_few_unseen_questions_means_new_ones_are_written(self):
		self._set("REUSETEST-A", ["Q1", "Q2", "Q3"])
		self.assertIsNone(reuse.pooled_practice(self.KEY, 3, "REUSETEST-A"))
