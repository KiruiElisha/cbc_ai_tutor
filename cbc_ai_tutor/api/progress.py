"""One learner's progress, as parents and teachers see it. Callers check access first."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, flt, now_datetime, strip_html

from cbc_ai_tutor.api import curriculum, sync


def summary(student: str) -> dict:
	"""The small card on a parent's or teacher's list."""
	week_ago = add_days(now_datetime(), -7)
	lessons_done = frappe.db.count(
		"Lesson Progress", {"student": student, "status": "Completed", "completed_on": [">=", week_ago]}
	)
	quiz = frappe.db.sql(
		"""select count(*) as attempts, avg(score) as average
		from `tabQuiz Submission` where student=%s and creation >= %s""",
		(student, week_ago),
		as_dict=True,
	)[0]
	last = frappe.db.sql(
		"""select max(t) from (
			select max(last_opened) as t from `tabLesson Progress` where student=%(s)s
			union all select max(creation) from `tabQuiz Submission` where student=%(s)s
			union all select max(date) from `tabAI Tutor Interaction` where student=%(s)s
		) x""",
		{"s": student},
	)[0][0]
	return {
		"lessons_completed_this_week": lessons_done,
		"quizzes_this_week": cint(quiz.attempts),
		"quiz_average_this_week": round(flt(quiz.average), 1) if quiz.attempts else None,
		"last_active": str(last) if last else None,
	}


def report(student: str) -> dict:
	"""The full progress screen: per learning area, recent work, competencies."""
	from cbc_ai_tutor.api.auth import learner_card

	scope = frappe.db.get_value(
		"Student", student, ["name", "student_name", "custom_grade", "custom_school"], as_dict=True
	)
	areas = curriculum.learning_areas(scope.custom_grade) if scope.custom_grade else []

	lessons = frappe.get_all(
		"Lesson",
		filters={"program": scope.custom_grade or "", "published": 1},
		fields=["name", "course", "quiz"],
		limit_page_length=0,
	)
	progress = {
		p.lesson: p
		for p in frappe.get_all(
			"Lesson Progress",
			filters={"student": student},
			fields=["lesson", "status", "progress", "time_spent", "course"],
			limit_page_length=0,
		)
	}
	best_scores = {
		r.quiz: flt(r.best)
		for r in frappe.db.sql(
			"select quiz, max(score) as best from `tabQuiz Submission` where student=%s group by quiz",
			student,
			as_dict=True,
		)
	}

	by_area = []
	for area in areas:
		area_lessons = [l for l in lessons if l.course == area["name"]]
		done = [l for l in area_lessons if (progress.get(l.name) or {}).get("status") == "Completed"]
		scores = [best_scores[l.quiz] for l in area_lessons if l.quiz and l.quiz in best_scores]
		by_area.append(
			{
				"course": area["name"],
				"title": area["title"],
				"lessons": len(area_lessons),
				"completed": len(done),
				"percent": round(100 * len(done) / len(area_lessons)) if area_lessons else 0,
				"quiz_average": round(sum(scores) / len(scores), 1) if scores else None,
				"minutes": round(
					sum(cint((progress.get(l.name) or {}).get("time_spent")) for l in area_lessons) / 60
				),
			}
		)

	lesson_titles = dict(frappe.get_all("Lesson", filters={"program": scope.custom_grade or ""}, fields=["name", "title"], as_list=True))
	recent_quizzes = frappe.get_all(
		"Quiz Submission",
		filters={"student": student},
		fields=["quiz", "lesson", "score", "status", "attempt_number", "time_completed", "creation"],
		order_by="creation desc",
		limit_page_length=15,
	)
	for row in recent_quizzes:
		row["lesson_title"] = lesson_titles.get(row.lesson)

	competencies = frappe.get_all(
		"Student Competency Progress",
		filters={"student": student},
		fields=["name", "learning_outcome", "performance_indicator", "status", "comments", "date", "teacher"],
		order_by="date desc, creation desc",
		limit_page_length=50,
	)
	outcome_text = {
		o.name: strip_html(o.description or "")[:240]
		for o in frappe.get_all(
			"Learning Outcome",
			filters={"name": ["in", [c.learning_outcome for c in competencies] or [""]]},
			fields=["name", "description"],
		)
	}
	for row in competencies:
		row["outcome"] = outcome_text.get(row.learning_outcome)

	assessments = frappe.get_all(
		"Continuous Assessment",
		filters={"student": student},
		fields=["name", "subject", "assessment_type", "score", "max_score", "date", "comments"],
		order_by="date desc",
		limit_page_length=30,
	)
	for row in assessments:
		row["comments"] = strip_html(row.comments or "")

	assignments = sync.visible_assignments(scope) if scope.custom_grade else []
	submitted = {
		s.assignment: s
		for s in frappe.get_all(
			"Assignment Submission",
			filters={"student": student},
			fields=["assignment", "status", "grade_given", "remarks", "submission_date"],
		)
	}
	work = []
	for a in assignments:
		s = submitted.get(a.name)
		work.append(
			{
				"assignment": a.name,
				"title": a.title,
				"type": a.assignment_type,
				"due_date": a.due_date,
				"status": s.status if s else "Not submitted",
				"grade_given": s.grade_given if s else None,
				"remarks": s.remarks if s else None,
				"submitted_on": s.submission_date if s else None,
			}
		)

	return {
		"learner": learner_card(student),
		"summary": summary(student),
		"learning_areas": by_area,
		"recent_quizzes": sync._stringify(recent_quizzes),
		"competencies": sync._stringify(competencies),
		"assessments": sync._stringify(assessments),
		"assignments": sync._stringify(work),
		"ai_quota": sync.ai_quota(student),
		"ai_questions_this_week": frappe.db.count(
			"AI Tutor Interaction", {"student": student, "date": [">=", add_days(now_datetime(), -7)]}
		),
	}
