"""First-run set-up: settings, CBC grades and learning areas, starter plans.

Seeding only adds what is missing, so it never overwrites a school's own edits.
Run it again on an existing site with:

    bench --site <site> execute cbc_ai_tutor.setup.install.seed
"""

import frappe

from cbc_ai_tutor.setup.curriculum import import_bundled

ROLES = ("Student", "Guardian", "Instructor")

GRADES = ["PP1", "PP2"] + [f"Grade {n}" for n in range(1, 13)]

# KICD learning areas per level, as rationalised in 2024. Editable in Desk.
LEARNING_AREAS = {
	"pre_primary": [
		"Language Activities",
		"Mathematical Activities",
		"Environmental Activities",
		"Creative Activities",
		"Religious Education Activities",
	],
	"lower_primary": [
		"English",
		"Kiswahili",
		"Indigenous Language",
		"Mathematics",
		"Environmental Activities",
		"Creative Activities",
		"Religious Education",
	],
	"upper_primary": [
		"English",
		"Kiswahili",
		"Mathematics",
		"Science and Technology",
		"Agriculture and Nutrition",
		"Social Studies",
		"Creative Arts",
		"Religious Education",
	],
	"junior_school": [
		"English",
		"Kiswahili",
		"Mathematics",
		"Integrated Science",
		"Agriculture and Nutrition",
		"Social Studies",
		"Pre-Technical Studies",
		"Creative Arts and Sports",
		"Religious Education",
	],
	"senior_school": [
		"English",
		"Kiswahili",
		"Core Mathematics",
		"Community Service Learning",
		"Physical Education",
		"Biology",
		"Chemistry",
		"Physics",
		"Computer Studies",
		"Agriculture",
		"Geography",
		"History and Citizenship",
		"Business Studies",
		"Religious Education",
	],
}

# Placeholder prices. Change them in Desk (Subscription Plan) before going live.
PLANS = [
	{
		"plan_name": "Monthly",
		"billing_period": "Monthly",
		"duration_days": 30,
		"display_order": 1,
		"price_kes": 499,
		"price_paypal": 4.99,
		"max_learners": 3,
		"ai_messages_per_day": 40,
		"tagline": "Every lesson and quiz for up to 3 children",
		"features": "All CBC lessons and quizzes\nWorks offline\nMwalimu AI tutor, 40 questions a day per child\nProgress reports for parents",
	},
	{
		"plan_name": "Termly",
		"billing_period": "Termly",
		"duration_days": 120,
		"display_order": 2,
		"price_kes": 1299,
		"price_paypal": 11.99,
		"max_learners": 4,
		"ai_messages_per_day": 60,
		"tagline": "A whole school term, about a month free",
		"features": "Everything in Monthly\nUp to 4 children\n60 AI tutor questions a day per child",
	},
	{
		"plan_name": "Yearly",
		"billing_period": "Yearly",
		"duration_days": 365,
		"display_order": 3,
		"price_kes": 3999,
		"price_paypal": 34.99,
		"max_learners": 6,
		"ai_messages_per_day": 0,
		"tagline": "The full school year at the best price",
		"features": "Everything in Termly\nUp to 6 children\nUnlimited AI tutor questions",
	},
]


def after_install():
	seed()


def after_migrate():
	ensure_roles()
	ensure_settings()
	seed_grades()
	import_bundled()


def seed():
	ensure_roles()
	ensure_settings()
	seed_grades()
	import_bundled()
	seed_plans()
	frappe.db.commit()


def ensure_roles():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 0}).insert(ignore_permissions=True)


def ensure_settings():
	"""Store the defaults and fill in the webhook URLs for this site."""
	doc = frappe.get_single("CBC Settings")
	for df in doc.meta.fields:
		if df.default and doc.get(df.fieldname) in (None, "") and df.fieldtype not in ("Password",):
			doc.set(df.fieldname, df.default)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.save()


def level_of(grade: str) -> str:
	if grade.startswith("PP"):
		return "pre_primary"
	number = int(grade.split()[-1])
	if number <= 3:
		return "lower_primary"
	if number <= 6:
		return "upper_primary"
	if number <= 9:
		return "junior_school"
	return "senior_school"


def seed_grades():
	for grade in GRADES:
		if frappe.db.exists("Program", grade):
			program = frappe.get_doc("Program", grade)
			if program.courses:
				continue
		else:
			program = frappe.get_doc(
				{
					"doctype": "Program",
					"program_name": grade,
					"program_abbreviation": grade.replace("Grade ", "G"),
				}
			)
		for area in LEARNING_AREAS[level_of(grade)]:
			course = f"{grade} {area}"
			if not frappe.db.exists("Course", course):
				frappe.get_doc({"doctype": "Course", "course_name": course}).insert(ignore_permissions=True)
			program.append("courses", {"course": course, "course_name": course, "required": 1})
		program.flags.ignore_permissions = True
		program.save()


def seed_plans():
	if frappe.db.count("Subscription Plan"):
		return
	for plan in PLANS:
		frappe.get_doc({"doctype": "Subscription Plan", "enabled": 1, **plan}).insert(ignore_permissions=True)
