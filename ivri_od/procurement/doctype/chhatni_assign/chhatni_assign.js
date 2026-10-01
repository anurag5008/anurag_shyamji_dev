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
	},
});
