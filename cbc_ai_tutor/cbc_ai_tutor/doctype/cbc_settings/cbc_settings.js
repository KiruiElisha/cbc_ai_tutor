// CBC Settings: check the AI tutor answers, and write the free lessons every learning area starts with now.
frappe.ui.form.on("CBC Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Check AI"), () => {
			frappe
				.call({ method: "cbc_ai_tutor.ai.providers.check", freeze: true, freeze_message: __("Asking the tutor…") })
				.then(({ message }) => {
					frappe.msgprint({
						title: __("The AI tutor answered"),
						indicator: "green",
						message: `<p>${frappe.utils.escape_html(message.text)}</p><p class="text-muted">${frappe.utils.escape_html(
							message.provider
						)} · ${frappe.utils.escape_html(message.model)}</p>`,
					});
				});
		});
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
