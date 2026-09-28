// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.listview_settings["Gate Entry"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Inside Mill"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Gate Entry", "in_out", "=", "In"],
				["Gate Entry", "inside_mill", "=", 1],
			]);
		});
	},
};

frappe.ui.form.on("Gate Entry", {
	refresh(frm) {
		frm.set_df_property("in_out", "hidden", 1);
		set_weighment_flag(frm);
	},
	in_purpose(frm) {
		set_weighment_flag(frm);
	},
});

function set_weighment_flag(frm) {
	const automatic = ["Paddy", "Rice"].includes(frm.doc.in_purpose);
	const is_gate_in = frm.doc.in_out === "In";
	frm.set_df_property("going_to_weighment", "read_only", automatic || !is_gate_in);
	if (automatic && !frappe.utils.cint(frm.doc.going_to_weighment)) {
		frm.set_value("going_to_weighment", 1);
	} else if (!is_gate_in && frappe.utils.cint(frm.doc.going_to_weighment)) {
		frm.set_value("going_to_weighment", 0);
	}
}
