# Copyright (c) 2026, Profezzo and contributors

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "grn_note")
	if not frappe.db.has_column("GRN Note", "total_bags"):
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
		doc = frappe.get_doc("GRN Note", row.name)
		doc._apply_wbm_bag_details(wbm)
		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True, ignore_version=True)
