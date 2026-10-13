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

function resolve_local_purchase_order(frm) {
	const party = (frm.doc.party_name || "").trim();
	const tp_no = (frm.doc.tp_no || "").trim();
	if (!party || tp_no) {
		return;
	}

	frappe.call({
		method: "ivri_od.procurement.doctype.local_paddy_purchase_order.local_paddy_purchase_order.get_open_purchase_orders_for_party",
		args: { party_name: party },
		callback(r) {
			const orders = r.message || [];
			if (orders.length === 1) {
				frm.set_value("local_purchase_order", orders[0].name);
				if (orders[0].commodity && !frm.doc.commodity) {
					frm.set_value("commodity", orders[0].commodity);
				}
			} else if (orders.length > 1) {
				// Multiple open POs found! Require explicit employee selection - do not auto-pick.
				let dialog = new frappe.ui.Dialog({
					title: __("Select Purchase Order for {0}", [party]),
					fields: [
						{
							fieldname: "po_select",
							fieldtype: "Select",
							label: __("Applicable Purchase Order"),
							reqd: 1,
							options: orders.map(po => ({
								label: `${po.name} | Date: ${po.order_date} | Qty: ${po.ordered_quantity} Qtl (Pending: ${po.pending_quantity} Qtl) | ${po.commodity || "Paddy"}`,
								value: po.name
							}))
						}
					],
					primary_action_label: __("Select PO"),
					primary_action(values) {
						dialog.hide();
						frm.set_value("local_purchase_order", values.po_select);
						const selected = orders.find(o => o.name === values.po_select);
						if (selected && selected.commodity && !frm.doc.commodity) {
							frm.set_value("commodity", selected.commodity);
						}
					}
				});
				dialog.show();
			}
		}
	});
}

frappe.ui.form.on("RST Details", {
	setup(frm) {
		frm.set_query("local_purchase_order", function() {
			let filters = {
				status: ["in", ["Open", "Partially Received"]],
			};
			let party = (frm.doc.party_name || "").trim();
			if (party) {
				filters["party_name"] = ["like", `%${party}%`];
			}
			return { filters: filters };
		});
	},
	refresh(frm) {
		sync_mill_requirement(frm);
	},
	tp_no(frm) {
		refresh_mill_and_agent_from_tp(frm);
	},
	party_name(frm) {
		refresh_mill_and_agent_from_tp(frm);
		if (!frm.doc.tp_no && !frm.doc.local_purchase_order) {
			resolve_local_purchase_order(frm);
		}
	},
	local_purchase_order(frm) {
		if (frm.doc.local_purchase_order) {
			frappe.db.get_value("Local Paddy Purchase Order", frm.doc.local_purchase_order, ["commodity", "party_name"], (r) => {
				if (r) {
					if (r.commodity && !frm.doc.commodity) {
						frm.set_value("commodity", r.commodity);
					}
				}
			});
		}
	}
});
