import frappe


def clean_up(doc, method=None):
	"""Progress belongs to the lesson; attempts and tutor chats outlive it."""
	frappe.db.delete("Lesson Progress", {"lesson": doc.name})
	for doctype in ("Quiz Submission", "AI Tutor Interaction"):
		frappe.db.set_value(doctype, {"lesson": doc.name}, "lesson", None, update_modified=False)
