// CBC Settings: write the free lessons every learning area starts with, now instead of tonight.
frappe.ui.form.on("CBC Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Write free lessons now"), () => {
			frappe
				.call({ method: "cbc_ai_tutor.ai.content.write_free_lessons" })
				.then(({ message }) => {
					frappe.show_alert({
						message: message.queued
							? __("Writing {0} free lessons in the background. Learners get them on their next sync.", [message.queued])
							: __("Every learning area already has its free lessons."),
						indicator: "green",
					});
				});
		});
	},
});
