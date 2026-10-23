// Copyright (c) 2026, Profezzo and contributors

frappe.ui.form.on("Chhatni", {
	season(frm) {
		try_resolve_pass_from_ppc_tp(frm);
	},
	ppc_name(frm) {
		try_resolve_pass_from_ppc_tp(frm);
	},
	tp_no(frm) {
		try_resolve_pass_from_ppc_tp(frm);
	},
	pass_unique_key(frm) {
		refresh_chhatni_values(frm);
	},
	chhatni_kg_per_qtl(frm) {
		refresh_chhatni_values(frm);
	},
	tp_quantity(frm) {
		refresh_chhatni_values(frm);
	},
});

// Preview only: the server calculates Net Weight and Chhatni again on save.
// Chhatni (KG) and (QT) are hidden on the form but kept for Mandi Book.
function refresh_chhatni_values(frm) {
	const pass_unique_key = (frm.doc.pass_unique_key || "").trim();
	frappe.call({
		method: "ivri_od.procurement.doctype.chhatni.chhatni.get_chhatni_preview",
		args: {
			pass_unique_key,
			chhatni_kg_per_qtl: frm.doc.chhatni_kg_per_qtl || 0,
			tp_quantity: frm.doc.tp_quantity || 0,
		},
		callback(r) {
			const data = r.message || {};
			for (const fieldname of ["net_weight", "chhatni_kg", "chhatni_qt", "received_chhatni_pct"]) {
				frm.set_value(fieldname, data[fieldname] || 0);
			}
		},
	});
}

// Same lookup as the Entry form (Season + PPC + TP No -> PPAS Transit Pass).
function try_resolve_pass_from_ppc_tp(frm) {
	const season = (frm.doc.season || "").trim();
	const ppc = (frm.doc.ppc_name || "").trim();
	const tp_no = (frm.doc.tp_no || "").trim();
	if (!season || !ppc || !tp_no) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.entry.entry.resolve_entry_pass_from_ppc_tp",
		args: { season, ppc_name: ppc, tp_no },
		freeze: true,
		freeze_message: __("Fetching Pass Unique Key…"),
		callback(r) {
			const data = r.message || {};
			if (!data.pass_unique_key) {
				frappe.msgprint({
					title: __("Transit pass not found"),
					message: __("No PPAS Transit Pass for this Season, PPC, and TP No."),
					indicator: "red",
				});
				frm.set_value("pass_unique_key", "");
				return;
			}
			frm.set_value("pass_unique_key", data.pass_unique_key);
			if (data.transit_pass_no) {
				frm.set_value("transit_pass_no", data.transit_pass_no);
			}
			frm.set_value("tp_quantity", data.quantity || 0);
			frm.set_value("pacs_name", data.pacs || "");
			frappe.show_alert({
				message: __("Pass Unique Key loaded from PPAS Transit Pass"),
				indicator: "green",
			});
		},
	});
}
