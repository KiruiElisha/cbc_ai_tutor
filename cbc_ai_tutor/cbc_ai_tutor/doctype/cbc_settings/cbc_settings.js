// CBC Settings: check the AI tutor answers, and write the free lessons every learning area starts with now.
frappe.ui.form.on("CBC Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Check AI"), () => {
			frappe
				.call({
					method: "cbc_ai_tutor.ai.providers.check",
					freeze: true,
					freeze_message: __("Asking the tutor…"),
				})
				.then(({ message }) => {
					// Every provider is asked at once; the list shows who answered and how fast.
					const esc = frappe.utils.escape_html;
					const rows = (message.providers || [])
						.map(
							(p) =>
								`<tr><td>${esc(p.provider)} · ${esc(p.model)}</td><td>${
									p.error
										? `<span class="text-danger">${esc(p.error)}</span>`
										: `${p.seconds}s`
								}</td></tr>`
						)
						.join("");
					frappe.msgprint({
						title: __("The AI tutor answered"),
						indicator: "green",
						message: `<p>${esc(message.text)}</p><table class="table table-sm">${rows}</table>`,
					});
				});
		});
		frm.add_custom_button(__("Write free lessons now"), () => {
			frappe
				.call({ method: "cbc_ai_tutor.ai.content.write_free_lessons" })
				.then(({ message }) => {
					frappe.show_alert({
						message: message.queued
							? __(
									"Writing {0} free lessons in the background. Learners get them on their next sync.",
									[message.queued]
							  )
							: __("Every learning area already has its free lessons."),
						indicator: "green",
					});
				});
		});
	},
});
