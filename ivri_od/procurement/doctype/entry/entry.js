// Copyright (c) 2026, Profezzo and contributors

frappe.ui.form.on("Entry", {
	season(frm) {
		try_resolve_pass_from_ppc_tp(frm);
	},
	ppc_name(frm) {
		try_resolve_pass_from_ppc_tp(frm);
	},
	tp_no(frm) {
		try_resolve_pass_from_ppc_tp(frm);
	},
	entry_quantity(frm) {
		update_total_amount(frm);
	},
	entry_price_per_quintal(frm) {
		update_total_amount(frm);
	},
});

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
					message: __(
						"No PPAS Transit Pass for this Season, PPC, and TP No."
					),
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

function update_total_amount(frm) {
	const total =
		flt(frm.doc.entry_quantity) *
		flt(frm.doc.entry_price_per_quintal);
	frm.set_value("total_amount", total);
}
