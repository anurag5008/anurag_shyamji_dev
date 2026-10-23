// Copyright (c) 2026, Profezzo and contributors

const PPAS_NEW_GROUP = __("Add");

// "New PPAS Data Extraction System" moved to Portal Data Extraction > Add > PPAS.
// "PPAS Transit Pass Import (Manual)" moved to the PPAS Details page > Manual Entry.
const PPAS_NEW_OPTIONS = [];

function setup_ppas_extraction_new_menu(page) {
	page.clear_primary_action();

	// Remove legacy custom dropdown (bad styling).
	page.custom_actions.find(".custom-btn-group.ppas-new-menu").remove();

	const $existing = page.get_inner_group_button(PPAS_NEW_GROUP);
	if ($existing.length) {
		$existing.remove();
	}

	PPAS_NEW_OPTIONS.forEach(({ label, doctype }) => {
		page.add_inner_button(label, () => frappe.new_doc(doctype), PPAS_NEW_GROUP);
	});

	if (PPAS_NEW_OPTIONS.length) {
		page.set_inner_btn_group_as_primary(PPAS_NEW_GROUP);
	}
}

frappe.listview_settings["PPAS Data Extraction"] = {
	onload(listview) {
		setup_ppas_extraction_new_menu(listview.page);

		listview.set_primary_action = function () {
			setup_ppas_extraction_new_menu(this.page);
		};
	},
};
