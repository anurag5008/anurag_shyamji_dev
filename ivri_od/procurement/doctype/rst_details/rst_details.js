// Copyright (c) 2026, Profezzo and contributors

function sync_mill_requirement(frm) {
	// Mill No is not mandatory while TP No is empty. It is fetched on save
	// only when Party Name is found and TP No is filled.
	frm.toggle_reqd("mill_name", false);
}

function refresh_mill_and_agent_from_tp(frm) {
	sync_mill_requirement(frm);
	const tp_no = (frm.doc.tp_no || "").trim();
	const party_name = (frm.doc.party_name || "").trim();
	// Mill is taken only when both TP No and Party Name can filter a transit pass.
	if (!tp_no || !party_name) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.rst_details.rst_details.fetch_mill_and_agent_from_tp",
		args: { tp_no, party_name },
		callback(r) {
			const data = r.message || {};
			if (data.error) {
				frappe.msgprint({ title: __("Transit Pass"), message: data.error, indicator: "orange" });
				return;
			}
			if (data.mill_name) {
				frm.set_value("mill_name", data.mill_name);
			}
			if (data.agent_name) {
				frm.set_value("agent_name", data.agent_name);
			}
			sync_mill_requirement(frm);
		},
	});
}

frappe.ui.form.on("RST Details", {
	refresh(frm) {
		sync_mill_requirement(frm);
	},
	tp_no(frm) {
		refresh_mill_and_agent_from_tp(frm);
	},
	party_name(frm) {
		refresh_mill_and_agent_from_tp(frm);
	},
});
