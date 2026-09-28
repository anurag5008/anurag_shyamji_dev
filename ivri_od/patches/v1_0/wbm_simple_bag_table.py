"""Simplify Weigh Bridge Bag Detail to Jute / Polythene rows."""

import frappe


def execute():
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_bag_detail")
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_measurement")

	child = "Weigh Bridge Bag Detail"
	for fieldname in (
		"jute_bags",
		"plastic_bags",
		"weight_per_jute_kg",
		"weight_per_polythene_kg",
	):
		if frappe.db.has_column(child, fieldname):
			frappe.db.sql(f"ALTER TABLE `tab{child}` DROP COLUMN `{fieldname}`")

	frappe.db.commit()
