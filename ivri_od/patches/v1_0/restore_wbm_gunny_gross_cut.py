"""Restore Gunny Gross / Gunny Cut fields on Weigh Bridge Measurement."""

import frappe


def execute():
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_measurement")

	if not frappe.db.has_column("Weigh Bridge Measurement", "gunny_type"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabWeigh Bridge Measurement`
			ADD COLUMN gunny_type varchar(140) DEFAULT 'Gunny Cut'
			"""
		)
	if not frappe.db.has_column("Weigh Bridge Measurement", "weight_per_gunny"):
		frappe.db.sql(
			"""
			ALTER TABLE `tabWeigh Bridge Measurement`
			ADD COLUMN weight_per_gunny decimal(21,9) NOT NULL DEFAULT 0
			"""
		)

	frappe.db.sql(
		"""
		UPDATE `tabWeigh Bridge Measurement`
		SET gunny_type = 'Gunny Cut'
		WHERE IFNULL(gunny_type, '') = ''
		"""
	)
	frappe.db.commit()
