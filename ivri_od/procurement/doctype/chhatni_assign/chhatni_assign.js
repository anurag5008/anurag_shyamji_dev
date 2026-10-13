// Copyright (c) 2026, Profezzo and contributors

function set_chhatni_percentage(frm) {
	const kg = flt(frm.doc.chutney_quantity_kg_per_quintal);
	frm.set_value("chutney_percentage", kg);
}

frappe.ui.form.on("Chhatni Assign", {
	chutney_quantity_kg_per_quintal(frm) {
		set_chhatni_percentage(frm);
	},
	refresh(frm) {
		if (frm.doc.chutney_quantity_kg_per_quintal && !frm.doc.chutney_percentage) {
			set_chhatni_percentage(frm);
		}
		frm.set_df_property("chhatni_history", "cannot_add_rows", 1);
		frm.set_df_property("chhatni_history", "cannot_delete_rows", 1);
	},
	after_save(frm) {
		if (!frm.doc.season || !frm.doc.ppc_name || !frm.doc.mill_name) {
			return;
		}
		frappe.show_alert(
			{
				message: __(
					"Matching Target Allocation records (same Season, PPC, Mill) were updated with this Chhatni."
				),
				indicator: "green",
			},
			5
		);
	},
});
