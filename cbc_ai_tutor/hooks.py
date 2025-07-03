app_name = "cbc_ai_tutor"
app_title = "CBC AI Tutor"
app_publisher = "ronoh"
app_description = "CBC App supported with AI"
app_email = "kiruielisha22@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "cbc_ai_tutor",
# 		"logo": "/assets/cbc_ai_tutor/logo.png",
# 		"title": "CBC AI Tutor",
# 		"route": "/cbc_ai_tutor",
# 		"has_permission": "cbc_ai_tutor.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/cbc_ai_tutor/css/cbc_ai_tutor.css"
# app_include_js = "/assets/cbc_ai_tutor/js/cbc_ai_tutor.js"

# include js, css files in header of web template
# web_include_css = "/assets/cbc_ai_tutor/css/cbc_ai_tutor.css"
# web_include_js = "/assets/cbc_ai_tutor/js/cbc_ai_tutor.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cbc_ai_tutor/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "cbc_ai_tutor/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "cbc_ai_tutor.utils.jinja_methods",
# 	"filters": "cbc_ai_tutor.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "cbc_ai_tutor.install.before_install"
# after_install = "cbc_ai_tutor.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "cbc_ai_tutor.uninstall.before_uninstall"
# after_uninstall = "cbc_ai_tutor.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cbc_ai_tutor.utils.before_app_install"
# after_app_install = "cbc_ai_tutor.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cbc_ai_tutor.utils.before_app_uninstall"
# after_app_uninstall = "cbc_ai_tutor.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cbc_ai_tutor.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"cbc_ai_tutor.tasks.all"
# 	],
# 	"daily": [
# 		"cbc_ai_tutor.tasks.daily"
# 	],
# 	"hourly": [
# 		"cbc_ai_tutor.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cbc_ai_tutor.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cbc_ai_tutor.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "cbc_ai_tutor.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "cbc_ai_tutor.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "cbc_ai_tutor.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cbc_ai_tutor.utils.before_request"]
# after_request = ["cbc_ai_tutor.utils.after_request"]

# Job Events
# ----------
# before_job = ["cbc_ai_tutor.utils.before_job"]
# after_job = ["cbc_ai_tutor.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"cbc_ai_tutor.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

