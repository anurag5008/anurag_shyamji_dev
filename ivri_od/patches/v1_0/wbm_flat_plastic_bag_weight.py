"""Flat jute / plastic bag weight fields on Weigh Bridge Measurement."""

import frappe

from ivri_od.patches.v1_0.reload_quality_check_doctype import execute as reload_doctypes


def execute():
	reload_doctypes()

	if frappe.db.has_column("Weigh Bridge Measurement", "bag_weight_details"):
		# Legacy child table removed from parent; weights migrated if present.
		if frappe.db.table_exists("Weigh Bridge Bag Detail"):
			for wbm in frappe.get_all("Weigh Bridge Measurement", pluck="name"):
				rows = frappe.get_all(
					"Weigh Bridge Bag Detail",
					filters={"parent": wbm},
					fields=["bag_type", "weight_per_bag_kg"],
				)
				if not rows:
					continue
				updates = {}
				for row in rows:
					bag_type = (row.bag_type or "").strip()
					if bag_type == "Jute":
						updates["weight_per_jute_bag_kg"] = row.weight_per_bag_kg
					elif bag_type in ("Polythene", "Plastic"):
						updates["weight_per_plastic_bag_kg"] = row.weight_per_bag_kg
				if updates:
					frappe.db.set_value(
						"Weigh Bridge Measurement",
						wbm,
						updates,
						update_modified=False,
					)

	frappe.db.commit()
