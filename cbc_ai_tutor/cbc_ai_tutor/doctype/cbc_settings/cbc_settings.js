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
		frm.add_custom_button(__("AI usage"), () => {
			// Answers, tokens and cost by provider for the last 30 days, and how each one is doing now.
			frappe.call({ method: "cbc_ai_tutor.ai.providers.usage", args: { days: 30 } }).then(({ message }) => {
				const esc = frappe.utils.escape_html;
				const rows = message.by_provider
					.map(
						(r) =>
							`<tr><td>${esc(r.provider)} · ${esc(r.model)}</td><td>${r.answers}</td><td>${
								r.cached || 0
							}</td><td>${(r.input_tokens || 0) + (r.output_tokens || 0)}</td><td>${
								r.cost_usd == null ? "–" : "US$" + r.cost_usd
							}</td></tr>`
					)
					.join("");
				const now = message.now
					.map(
						(n) =>
							`<tr><td>${esc(n.provider)} · ${esc(n.model)}</td><td>${esc(n.tier)}</td><td>${
								n.seconds == null ? "–" : n.seconds.toFixed(1) + "s"
							}</td><td>${n.today}</td><td>${
								n.resting ? "Resting" : n.failures_in_a_row ? n.failures_in_a_row + " failures" : "OK"
							}</td></tr>`
					)
					.join("");
				frappe.msgprint({
					title: __("AI usage, last {0} days", [message.days]),
					wide: true,
					message:
						`<table class="table table-sm"><tr><th>Provider</th><th>Answers</th><th>Reused</th><th>Tokens</th><th>Cost</th></tr>${rows}</table>` +
						`<h5>Now</h5><table class="table table-sm"><tr><th>Provider</th><th>Tier</th><th>Usual time</th><th>Today</th><th>State</th></tr>${now}</table>`,
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
