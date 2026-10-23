// Copyright (c) 2026, Profezzo and contributors

function sync_mill_requirement(frm) {
	// Mill No is not mandatory while TP No is empty. It is fetched on save
	// only when Party Name is found and TP No is filled.
	frm.toggle_reqd("mill_name", false);
}

function refresh_tp_details(frm) {
	sync_mill_requirement(frm);
	const tp_no = (frm.doc.tp_no || "").trim();
	const party_name = (frm.doc.party_name || "").trim();
	// Only the reply for the latest TP No / Party Name may set the status.
	const request_id = (frm.__tp_details_request_id || 0) + 1;
	frm.__tp_details_request_id = request_id;

	frappe.call({
		method: "ivri_od.procurement.doctype.rst_details.rst_details.fetch_mill_and_agent_from_tp",
		args: { tp_no, party_name, entry_datetime: frm.doc.entry_datetime || "" },
		callback(r) {
			if (request_id !== frm.__tp_details_request_id) {
				return;
			}
			const data = r.message || {};
			if (data.tp_status !== undefined) {
				frm.set_value("tp_status", data.tp_status);
			}
			if (data.mill_name !== undefined) {
				frm.set_value("mill_name", data.mill_name);
			}
			if (data.agent_name !== undefined) {
				frm.set_value("agent_name", data.agent_name);
			}
			for (const fieldname of ["season_code", "rst_unique_key", "tp_quantity"]) {
				if (data[fieldname] !== undefined && frm.fields_dict[fieldname]) {
					frm.set_value(fieldname, data[fieldname]);
				}
			}
			show_rst_unique_key_status(frm, data.key_message || "");
			if (data.notification) {
				frappe.msgprint({
					title: __(data.tp_status || "Status"),
					message: __(data.notification),
					indicator: "orange",
				});
			}
			if (data.validation_message) {
				frappe.msgprint({
					title: __("Transit Pass"),
					message: __(data.validation_message),
					indicator: "red",
				});
			}
			sync_mill_requirement(frm);
		},
	});
}

// The site hides empty read-only fields; keep these visible so staff see they are empty.
function always_show_read_only(frm, fieldnames) {
	for (const fieldname of fieldnames) {
		const field = frm.fields_dict[fieldname];
		if (field && !field.df.get_status) {
			field.df.get_status = () => "Read";
			field.refresh();
		}
	}
}

// Say why the key is missing.
// message: the server's reason after a lookup; undefined on load, when the saved values decide.
function show_rst_unique_key_status(frm, message) {
	frm.set_intro("");
	if (!frm.fields_dict.rst_unique_key) {
		return;
	}
	if (message === undefined && !frm.is_new() && !frm.doc.rst_unique_key) {
		if (!frm.doc.season_code) {
			message = __(
				"Season Not Configured. No Season Master has a Start Date - End Date range that covers this RST Date & Time. Set the season dates, then save this RST again."
			);
		} else if (frm.doc.tp_status === "TP Received") {
			message = __(
				"The Transit Pass for this TP No and PPC is not in season {0} of the RST Date & Time. Check the RST Date & Time or the Season Master dates.",
				[frm.doc.season_code]
			);
		}
	}
	if (message) {
		frm.set_intro(__("RST Unique Key is empty: {0}", [message]), "orange");
	}
}

// Hidden, for future RST-based Chhatni entry. Same rules as chhatni_from_rate on the server,
// which calculates these again on save. Not used by Mandi Book yet.
function calculate_rst_chhatni(frm) {
	if (!frm.fields_dict.chhatni_qt) {
		return;
	}
	const net_weight = flt(frm.doc.net_paddy_weight_qt, 3);
	const tp_quantity = flt(frm.doc.tp_quantity);
	let chhatni_kg = 0;
	let chhatni_qt = 0;
	let received_pct = 0;
	if (net_weight > 0) {
		chhatni_kg = flt(net_weight * flt(frm.doc.chhatni_kg_per_qtl), 3);
		chhatni_qt = flt(chhatni_kg / 100, 3);
		received_pct = tp_quantity > 0 ? flt((chhatni_qt / tp_quantity) * 100, 2) : 0;
	}
	frm.set_value({ chhatni_kg, chhatni_qt, received_chhatni_pct: received_pct });
}

frappe.ui.form.on("RST Details", {
	refresh(frm) {
		sync_mill_requirement(frm);
		frm.toggle_display("local_purchase_order", Boolean(frm.doc.local_purchase_order));
		always_show_read_only(frm, ["season_code", "rst_unique_key"]);
		show_rst_unique_key_status(frm);
	},
	tp_no(frm) {
		refresh_tp_details(frm);
	},
	entry_datetime(frm) {
		refresh_tp_details(frm);
	},
	party_name(frm) {
		refresh_tp_details(frm);
	},
	net_paddy_weight_qt(frm) {
		calculate_rst_chhatni(frm);
	},
	chhatni_kg_per_qtl(frm) {
		calculate_rst_chhatni(frm);
	},
	tp_quantity(frm) {
		calculate_rst_chhatni(frm);
	},
});
