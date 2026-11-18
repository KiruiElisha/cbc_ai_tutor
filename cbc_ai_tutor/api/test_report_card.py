"""The parent's report card and weekly email: one honest sentence, the best area, what to practise."""

import unittest

from cbc_ai_tutor.api.progress import highlights


def _area(title, lessons=10, completed=0, quiz=None):
	return {
		"title": title,
		"lessons": lessons,
		"completed": completed,
		"percent": round(100 * completed / lessons) if lessons else 0,
		"quiz_average": quiz,
	}


AMINA = {"first_name": "Amina", "name": "Amina Wanjiru"}


class TestReportCard(unittest.TestCase):
	def test_a_busy_week_names_the_lessons_and_the_best_area(self):
		h = highlights(
			AMINA,
			{"lessons_completed_this_week": 6, "last_active": "2026-11-17"},
			[_area("Mathematics", completed=4, quiz=78), _area("English", completed=2, quiz=85)],
		)
		self.assertEqual(h["headline"], "Amina finished 6 lessons this week and is doing best in English.")
		self.assertEqual(h["strong"]["title"], "English")

	def test_a_weak_quiz_average_comes_first_to_practise_with_its_reason(self):
		h = highlights(
			AMINA,
			{"lessons_completed_this_week": 1, "last_active": "2026-11-17"},
			[
				_area("Mathematics", completed=3, quiz=45),
				_area("English", completed=5, quiz=90),
				_area("Science"),
			],
		)
		self.assertEqual(h["practise"][0], {"title": "Mathematics", "why": "quiz average 45%"})
		self.assertEqual(h["practise"][1], {"title": "Science", "why": "not started yet"})

	def test_one_lesson_is_said_in_the_singular(self):
		h = highlights(AMINA, {"lessons_completed_this_week": 1}, [_area("English", completed=1)])
		self.assertTrue(h["headline"].startswith("Amina finished 1 lesson this week"))

	def test_a_quiet_week_says_so_kindly_and_a_new_learner_is_invited_to_start(self):
		quiet = highlights(
			AMINA, {"lessons_completed_this_week": 0, "last_active": "2026-11-01"}, [_area("English")]
		)
		self.assertIn("has not finished a lesson this week yet", quiet["headline"])
		new = highlights(AMINA, {"lessons_completed_this_week": 0, "last_active": None}, [_area("English")])
		self.assertIn("has not started yet", new["headline"])
		self.assertIsNone(new["strong"])
