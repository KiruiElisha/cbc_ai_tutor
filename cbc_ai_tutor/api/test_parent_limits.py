"""A parent's own limits for a child: quiet hours (even overnight) and a lower Mwalimu limit."""

import datetime
import unittest
from unittest.mock import patch

import frappe

from cbc_ai_tutor.api import tutor


def _at(hour, minute=0):
	return datetime.datetime(2026, 11, 18, hour, minute)


class TestQuietHours(unittest.TestCase):
	def _quiet(self, start, end, now):
		with patch.object(frappe.db, "get_value", return_value=(start, end)):
			return tutor.quiet_until("STU-1", now=now)

	def test_mwalimu_rests_inside_quiet_hours_and_says_until_when(self):
		self.assertEqual(self._quiet("13:00:00", "15:00:00", _at(14)), "15:00")
		self.assertIsNone(self._quiet("13:00:00", "15:00:00", _at(15)))

	def test_bedtime_runs_past_midnight(self):
		self.assertEqual(self._quiet("21:00:00", "06:00:00", _at(22, 30)), "06:00")
		self.assertEqual(self._quiet("21:00:00", "06:00:00", _at(5, 59)), "06:00")
		self.assertIsNone(self._quiet("21:00:00", "06:00:00", _at(12)))

	def test_no_quiet_hours_set_means_always_available(self):
		self.assertIsNone(self._quiet(None, None, _at(23)))
