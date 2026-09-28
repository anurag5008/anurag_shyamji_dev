// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Entry", {
	onload(frm) {
		setup_pass_unique_key_autocomplete(frm);
	},
	refresh(frm) {
		setup_pass_unique_key_autocomplete(frm);
	},
	pass_unique_key(frm) {
		load_transit_pass_details(frm);
	},
	entry_quantity(frm) {
		update_total_amount(frm);
	},
	entry_price_per_quintal(frm) {
		update_total_amount(frm);
	},
});

function setup_pass_unique_key_autocomplete(frm) {
	const field = frm.fields_dict.pass_unique_key;
	if (!field || field.pass_unique_key_autocomplete_setup) {
		return;
	}
	field.pass_unique_key_autocomplete_setup = true;

	const load_options = (txt = "") => {
		frappe.call({
			method:
				"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.get_pass_unique_key_autocomplete",
			args: { txt, limit: 25 },
			callback(r) {
				if (field.set_data) {
					field.set_data(r.message || []);
				}
			},
		});
	};

	load_options("");
	field.$input?.on("focus", () => load_options(field.get_value() || ""));
	field.$input?.on(
		"input",
		frappe.utils.debounce(() => load_options(field.$input.val() || ""), 300)
	);
}

function load_transit_pass_details(frm) {
	const key = (frm.doc.pass_unique_key || "").trim();
	if (!key) {
		return;
	}
	frappe.db.get_value(
		"PPAS Transit Pass",
		{ pass_unique_key: key },
		["transit_pass_no", "quantity", "pacs"],
		(r) => {
			if (!r) {
				return;
			}
			if (r.transit_pass_no) {
				frm.set_value("transit_pass_no", r.transit_pass_no);
			}
			frm.set_value("tp_quantity", r.quantity || 0);
			frm.set_value("pacs_name", r.pacs || "");
		}
	);
}

function update_total_amount(frm) {
	const total =
		frappe.utils.flt(frm.doc.entry_quantity) *
		frappe.utils.flt(frm.doc.entry_price_per_quintal);
	frm.set_value("total_amount", total);
}
