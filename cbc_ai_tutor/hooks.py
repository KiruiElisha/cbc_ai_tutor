app_name = "cbc_ai_tutor"
app_title = "CBC AI Tutor"
app_publisher = "ronoh"
app_description = "CBC App supported with AI"
app_email = "kiruielisha22@gmail.com"
app_license = "mit"

required_apps = ["education"]

after_install = "cbc_ai_tutor.setup.install.after_install"
after_migrate = "cbc_ai_tutor.setup.install.after_migrate"

# The desktop and mobile apps send `Authorization: Bearer cbc_...` device tokens.
auth_hooks = ["cbc_ai_tutor.api.auth.validate_token"]

doc_events = {
	"Student": {
		"after_insert": "cbc_ai_tutor.events.student.enroll",
		"on_update": "cbc_ai_tutor.events.student.enroll_on_grade_change",
	},
	"Lesson": {
		"on_trash": "cbc_ai_tutor.events.lesson.clean_up",
	},
}

doctype_js = {"Program": "public/js/program.js"}

scheduler_events = {
	"cron": {
		"*/10 * * * *": ["cbc_ai_tutor.tasks.reconcile_pending_payments"],
	},
	"daily": [
		"cbc_ai_tutor.tasks.expire_subscriptions",
		"cbc_ai_tutor.tasks.send_renewal_reminders",
		"cbc_ai_tutor.tasks.purge_device_sessions",
		"cbc_ai_tutor.tasks.purge_sync_receipts",
		"cbc_ai_tutor.ai.content.daily",
	],
}

fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["dt", "in", ["Student", "Instructor"]]],
	},
	"Server Script",
]
