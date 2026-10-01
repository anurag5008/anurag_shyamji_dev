// Copyright (c) 2026, Profezzo and contributors

function apply_latest_chutney(frm, data) {
	if (!data || !data.name) {
		frm.set_value("latest_chutney_assign", "");
		frm.set_value("latest_chutney_season", "");
		frm.set_value("latest_chutney_kg_per_quintal", 0);
		frm.set_value("latest_chutney_percentage", 0);
		return;
	}
	frm.set_value("latest_chutney_assign", data.name);
	frm.set_value("latest_chutney_season", data.season);
	frm.set_value("latest_chutney_kg_per_quintal", data.chutney_quantity_kg_per_quintal);
	frm.set_value("latest_chutney_percentage", data.chutney_percentage);
	frm.set_value("chhatni", data.chutney_quantity_kg_per_quintal || 0);
}

function refresh_latest_chutney(frm) {
	if (!frm.doc.ppc_name || !frm.doc.mill_name) {
		apply_latest_chutney(frm, null);
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.target_allocation.target_allocation.fetch_latest_chutney",
		args: {
			ppc_name: frm.doc.ppc_name,
			mill_name: frm.doc.mill_name,
			season: frm.doc.season || "",
		},
		callback(r) {
			apply_latest_chutney(frm, r.message);
		},
	});
}

frappe.ui.form.on("Target Allocation", {
	setup(frm) {
		frm.set_query("agent_name", () => ({
			filters: { is_active: 1 },
		}));
	},

	season(frm) {
		refresh_latest_chutney(frm);
	},

	ppc_name(frm) {
		refresh_latest_chutney(frm);
	},

	mill_name(frm) {
		refresh_latest_chutney(frm);
	},

	refresh(frm) {
		if (frm.doc.ppc_name && frm.doc.mill_name && !frm.is_new()) {
			refresh_latest_chutney(frm);
		}
	},
});
