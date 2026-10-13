# Copyright (c) 2026, Profezzo and contributors

import frappe

from ivri_od.procurement.doctype.grn_note.grn_note import _wbm_bag_counts_from_child_table


def execute():
	frappe.reload_doc("procurement", "doctype", "grn_note")

	frappe.db.delete(
		"Weigh Bridge Bag Detail",
		{"parenttype": "GRN Note", "parentfield": "bag_weight_details"},
	)

	if not frappe.db.has_column("GRN Note", "jute_bags"):
		return

	rows = frappe.get_all(
		"GRN Note",
		filters={"weigh_bridge_measurement": ["!=", ""]},
		fields=["name", "weigh_bridge_measurement"],
	)
	for row in rows:
		wbm = (row.weigh_bridge_measurement or "").strip()
		if not wbm:
			continue
		jute, plastic, total = _wbm_bag_counts_from_child_table(wbm)
		frappe.db.set_value(
			"GRN Note",
			row.name,
			{"jute_bags": jute, "plastic_bags": plastic, "total_bags": total},
			update_modified=False,
		)
