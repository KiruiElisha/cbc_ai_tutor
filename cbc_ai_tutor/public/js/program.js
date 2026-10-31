frappe.ui.form.on("Program", {
	refresh(frm) {
		if (frm.is_new()) return;
		// One AI call per sub-strand; every learner in the grade then reads the lesson for free.
		frm.add_custom_button(__("Write missing lessons"), () => {
			frappe.call({
				method: "cbc_ai_tutor.ai.content.write_grade",
				args: { grade: frm.doc.name },
				callback: ({ message }) =>
					frappe.msgprint(
						message.queued
							? __("Writing {0} lessons in the background. They appear as drafts in Lesson.", [message.queued])
							: __("Every sub-strand in {0} already has a lesson.", [frm.doc.name]),
					),
			});
		});
	},
});
