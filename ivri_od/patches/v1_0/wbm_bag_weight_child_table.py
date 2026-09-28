"""Reload WBM bag weight child table and drop legacy gunny / actual bags fields."""

import frappe


def execute():
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_bag_detail")
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_measurement")

	for fieldname in ("actual_bags_arrived", "gunny_type", "weight_per_gunny"):
		if frappe.db.has_column("Weigh Bridge Measurement", fieldname):
			frappe.db.sql(
				f"ALTER TABLE `tabWeigh Bridge Measurement` DROP COLUMN `{fieldname}`"
			)

	frappe.db.commit()
