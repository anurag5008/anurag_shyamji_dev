// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Season Mapping", {
	refresh(frm) {
		fetch_target_allocation(frm);
		fetch_grn_paddy_procured(frm);
	},
	season(frm) {
		fetch_target_allocation(frm);
		fetch_grn_paddy_procured(frm);
	},
	ppc_name(frm) {
		fetch_target_allocation(frm);
		fetch_grn_paddy_procured(frm);
	},
	mill_name(frm) {
		fetch_target_allocation(frm);
		fetch_grn_paddy_procured(frm);
	},
	season_quantity(frm) {
		update_collection_point_quantities(frm);
	},
	rice_yield(frm) {
		update_collection_point_quantities(frm);
	},
	collection_point_details_add(frm) {
		fetch_grn_paddy_procured(frm);
	},
});

frappe.ui.form.on("Season Mapping Collection Point", {
	paddy_proportion(frm) {
		fetch_grn_paddy_procured(frm);
	},
});

function fetch_target_allocation(frm) {
	if (!frm.doc.season || !frm.doc.ppc_name || !frm.doc.mill_name) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.season_mapping.season_mapping.fetch_target_allocation",
		args: {
			season: frm.doc.season,
			ppc_name: frm.doc.ppc_name,
			mill_name: frm.doc.mill_name,
		},
		callback(r) {
			const data = r.message || {};
			if (!data.target_quantity && data.target_quantity !== 0) {
				return;
			}
			if (!Object.keys(data).length) {
				return;
			}
			frm.set_value("season_quantity", data.target_quantity);
			frm.set_value("agent_name", data.agent_name || "");
			frm.set_value("chhatni", data.chhatni || 0);
		},
	});
}

function fetch_grn_paddy_procured(frm) {
	if (!frm.doc.season || !frm.doc.ppc_name || !frm.doc.mill_name) {
		update_collection_point_quantities(frm);
		return;
	}
	const request_id = (frm._grn_paddy_request_id || 0) + 1;
	frm._grn_paddy_request_id = request_id;
	frappe.call({
		method: "ivri_od.procurement.doctype.season_mapping.season_mapping.get_grn_paddy_procured",
		args: {
			season: frm.doc.season,
			ppc_name: frm.doc.ppc_name,
			mill_name: frm.doc.mill_name,
		},
	}).then((r) => {
		if (request_id !== frm._grn_paddy_request_id || r.message == null) return;
		const total_paddy = flt(r.message);
		const updates = (frm.doc.collection_point_details || []).map((row) =>
			frappe.model.set_value(
				row.doctype,
				row.name,
				"paddy_procured_till_date",
				flt((total_paddy * flt(row.paddy_proportion)) / 100, 3),
			),
		);
		Promise.all(updates).then(() => update_collection_point_quantities(frm));
	});
}

function update_collection_point_quantities(frm) {
	const season_quantity = flt(frm.doc.season_quantity);
	const rice_yield = flt(frm.doc.rice_yield);
	const updates = (frm.doc.collection_point_details || []).map((row) => {
		const rice_due_till_date = flt((flt(row.paddy_procured_till_date) / 100) * rice_yield, 3);
		const remaining_balance = flt(
			(season_quantity / 100) * (rice_yield / 100) * flt(row.paddy_proportion) -
			rice_due_till_date,
			3,
		);
		return Promise.all([
			frappe.model.set_value(row.doctype, row.name, "rice_due_till_date", rice_due_till_date),
			frappe.model.set_value(row.doctype, row.name, "remaining_balance", remaining_balance),
		]);
	});
	Promise.all(updates).then(() => frm.refresh_field("collection_point_details"));
}
