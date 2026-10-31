frappe.listview_settings["Strand"] = {
	onload(listview) {
		// CSV columns: grade, learning_area, strand, sub_strand, outcome, competency (cbc_ai_tutor.setup.curriculum).
		listview.page.add_inner_button(__("Import curriculum"), () => {
			new frappe.ui.FileUploader({
				restrictions: { allowed_file_types: [".csv"] },
				on_success(file) {
					frappe.call({
						method: "cbc_ai_tutor.setup.curriculum.import_file",
						args: { file_url: file.file_url },
						freeze: true,
						freeze_message: __("Importing the curriculum…"),
						callback: ({ message: added }) => {
							frappe.msgprint(
								__("Added {0} strands, {1} sub-strands and {2} learning outcomes.", [
									added.Strand,
									added["Sub-strand"],
									added["Learning Outcome"],
								]),
							);
							listview.refresh();
						},
					});
				},
			});
		});
	},
};
