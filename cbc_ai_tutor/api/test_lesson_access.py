"""Without a plan a learner still has lessons to open, and a topic with no lesson can be asked for."""

import json
import unittest
from unittest.mock import patch

import frappe

from cbc_ai_tutor.api import common, curriculum, sync

GRADE = "ACCESSTEST Grade 4"
COURSE = "ACCESSTEST Grade 4 Mathematics"
REPLY = {
	"title": "Fractions as equal parts",
	"summary": "A fraction is a part of a whole.",
	"body": "When Mama cuts a chapati into four equal pieces, each piece is one quarter. " * 6,
	"key_vocabulary": ["fraction"],
	"minutes": 20,
	"quiz": [{"question": f"Q{i}?", "options": ["a", "b", "c", "d"], "answer": 0} for i in range(3)],
}


class TestLessonAccess(unittest.TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.get_doc({"doctype": "Course", "course_name": COURSE}).insert()
		program = frappe.get_doc({"doctype": "Program", "program_name": GRADE, "program_abbreviation": "AT4"})
		program.append("courses", {"course": COURSE})
		program.insert()
		self.strands = [
			frappe.get_doc({"doctype": "Strand", "strand_name": t, "subject": COURSE, "order": i}).insert()
			for i, t in ((2, "Measurement"), (1, "Numbers"))
		]
		self.subs = {
			s.strand_name: frappe.get_doc({"doctype": "Sub-strand", "name1": f"{s.strand_name} topic", "strand": s.name, "order": 1}).insert()
			for s in self.strands
		}
		frappe.db.set_single_value("CBC Settings", "free_lessons_per_area", 1)
		frappe.db.set_single_value("CBC Settings", "learner_lesson_requests", 1)

	def tearDown(self):
		frappe.db.rollback()

	def lesson(self, strand, title, order=1, published=1, is_free=0):
		s = next(x for x in self.strands if x.strand_name == strand)
		return frappe.get_doc({
			"doctype": "Lesson", "title": title, "program": GRADE, "course": COURSE, "strand": s.name,
			"sub_strand": self.subs[strand].name, "lesson_order": order, "published": published, "is_free": is_free,
		}).insert().name

	def test_the_first_lessons_of_each_area_are_free_in_curriculum_order(self):
		later = self.lesson("Measurement", "Length")           # strand order 2
		first = self.lesson("Numbers", "Counting")             # strand order 1: comes first
		ticked = self.lesson("Measurement", "Mass", order=2, is_free=1)
		self.lesson("Numbers", "Draft", order=2, published=0)
		self.assertEqual(curriculum.free_lessons(GRADE), {first, ticked})
		rows = {r["name"]: r for r in curriculum.lessons(GRADE, entitled=False)}
		self.assertEqual((rows[first]["locked"], rows[first]["is_free"]), (0, 1))
		self.assertEqual(rows[later]["locked"], 1)
		self.assertIsNone(rows[later]["body"])

	def test_a_free_lesson_is_resent_on_every_pull_without_a_plan(self):
		first = self.lesson("Numbers", "Counting")
		frappe.db.set_value("Lesson", first, "modified", "2001-01-01 00:00:00", update_modified=False)
		rows = curriculum.lessons(GRADE, entitled=False, since="2020-01-01 00:00:00")
		self.assertEqual([r["name"] for r in rows], [first])
		self.assertEqual(curriculum.lessons(GRADE, entitled=True, since="2020-01-01 00:00:00"), [])

	def ask(self, sub, entitled=True):
		ent = frappe._dict(active=entitled)
		scope = frappe._dict(name="S1", custom_grade=GRADE)
		answer = {"text": json.dumps(REPLY), "provider": "test", "model": "", "input_tokens": 0, "output_tokens": 0}
		with (
			patch.object(common, "current_learner", return_value="S1"),
			patch.object(common, "entitlement_for_student", return_value=ent),
			patch.object(sync, "_learner_scope", return_value=scope),
			patch("cbc_ai_tutor.ai.providers.complete", return_value=answer) as call,
			patch.object(frappe.db, "commit"),  # tearDown rolls everything back
		):
			return sync.request_lesson(sub), call

	def test_a_topic_without_a_lesson_is_written_once_and_published(self):
		frappe.cache.delete_value(f"cbc:lesson-requests:S1:{frappe.utils.nowdate()}")
		sub = self.subs["Numbers"].name
		out, call = self.ask(sub)
		self.assertEqual(out["written"], 1)
		self.assertEqual(frappe.db.get_value("Lesson", out["lesson"], ["sub_strand", "published"]), (sub, 1))
		again, call = self.ask(sub)
		self.assertEqual((again["lesson"], again["written"]), (out["lesson"], 0))
		call.assert_not_called()

	def test_without_a_plan_only_a_free_lesson_can_be_asked_for(self):
		frappe.cache.delete_value(f"cbc:lesson-requests:S1:{frappe.utils.nowdate()}")
		out, _call = self.ask(self.subs["Numbers"].name, entitled=False)   # the area's one free lesson
		self.assertEqual(out["written"], 1)
		with self.assertRaises(common.SubscriptionRequired):
			self.ask(self.subs["Measurement"].name, entitled=False)

	def test_a_topic_outside_the_grade_is_refused(self):
		other = frappe.get_doc({"doctype": "Course", "course_name": "ACCESSTEST Other"}).insert()
		strand = frappe.get_doc({"doctype": "Strand", "strand_name": "X", "subject": other.name}).insert()
		sub = frappe.get_doc({"doctype": "Sub-strand", "name1": "Y", "strand": strand.name}).insert()
		with self.assertRaises(frappe.ValidationError):
			self.ask(sub.name)


class TestFreeLessonWriting(unittest.TestCase):
	setUp = TestLessonAccess.setUp
	tearDown = TestLessonAccess.tearDown
	lesson = TestLessonAccess.lesson

	def test_each_area_gets_its_free_lessons_written_once_in_curriculum_order(self):
		from cbc_ai_tutor.ai import content

		frappe.db.set_single_value("CBC Settings", "free_lessons_per_area", 1)
		mine = [m for m in content.free_lessons_missing() if frappe.db.get_value("Sub-strand", m[0], "strand") in {s.name for s in self.strands}]
		self.assertEqual(mine, [(self.subs["Numbers"].name, None)])     # Numbers comes before Measurement
		answer = {"text": json.dumps(REPLY), "provider": "test", "model": "", "input_tokens": 0, "output_tokens": 0}
		with (
			patch("cbc_ai_tutor.ai.content.free_lessons_missing", return_value=mine),
			patch("cbc_ai_tutor.ai.providers.complete", return_value=answer),
			patch.object(frappe.db, "commit"),
		):
			content.write_free()
		lesson = frappe.db.get_value("Lesson", {"sub_strand": self.subs["Numbers"].name}, ["published", "is_free"])
		self.assertEqual(lesson, (1, 1))
		self.assertNotIn(self.subs["Numbers"].name, [m[0] for m in content.free_lessons_missing()])

	def test_a_draft_is_published_instead_of_written_again(self):
		from cbc_ai_tutor.ai import content

		draft = self.lesson("Numbers", "Counting", published=0)
		mine = [m for m in content.free_lessons_missing() if m[1] == draft]
		self.assertEqual(mine, [(self.subs["Numbers"].name, draft)])
		with patch("cbc_ai_tutor.ai.providers.complete") as call, patch.object(frappe.db, "commit"), \
				patch("cbc_ai_tutor.ai.content.free_lessons_missing", return_value=mine):
			content.write_free()
		call.assert_not_called()
		self.assertEqual(frappe.db.get_value("Lesson", draft, ["published", "is_free"]), (1, 1))
