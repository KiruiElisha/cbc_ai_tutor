// Copyright (c) 2025, ronoh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Sub-strand", {
	refresh(frm) {
		if (frm.is_new()) return;
		// One AI call writes the lesson and quiz that every learner then reads (cbc_ai_tutor.ai.content).
		frm.add_custom_button(__("Write lesson with AI"), () => {
			frappe.call({
				method: "cbc_ai_tutor.ai.content.write_for",
				args: { sub_strand: frm.doc.name },
				freeze: true,
				freeze_message: __("Writing the lesson and its quiz…"),
				callback: (r) => r.message && frappe.set_route("Form", "Lesson", r.message.lesson),
			});
		});
	},
});
