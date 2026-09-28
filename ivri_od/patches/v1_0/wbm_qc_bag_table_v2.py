"""Restore QC bag child table and backfill from Quality Check."""

import frappe

from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	build_bag_details_from_qc,
	get_effective_truck_no,
	get_quality_check_for_wbm,
)


def execute():
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_bag_detail")
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_measurement")

	for fieldname in (
		"jute_bags_qc",
		"plastic_bags_qc",
		"weight_per_jute_bag_kg",
		"weight_per_plastic_bag_kg",
	):
		if frappe.db.has_column("Weigh Bridge Measurement", fieldname):
			frappe.db.sql(
				f"ALTER TABLE `tabWeigh Bridge Measurement` DROP COLUMN `{fieldname}`"
			)

	for row in frappe.get_all(
		"Weigh Bridge Measurement",
		fields=["name", "actual_truck_no", "truck_no_in_tp", "quality_check"],
	):
		data = get_quality_check_for_wbm(
			actual_truck_no=row.actual_truck_no,
			truck_no_in_tp=row.truck_no_in_tp,
			wbm_name=row.name,
		)
		qc = (data.get("quality_check") or row.quality_check or "").strip()
		if not qc:
			continue

		bag_rows = build_bag_details_from_qc(qc)
		if not bag_rows:
			continue

		doc = frappe.get_doc("Weigh Bridge Measurement", row.name)
		doc.bag_weight_details = []
		for bag in bag_rows:
			child = doc.append("bag_weight_details", {})
			child.jute_bags = bag["jute_bags"]
			child.plastic_bags = bag["plastic_bags"]
			child.weight_per_jute_kg = bag["weight_per_jute_kg"]
			child.weight_per_plastic_kg = bag["weight_per_plastic_kg"]
			child.gunny_weight_qt = bag["gunny_weight_qt"]

		updates = {}
		if (doc.quality_check or "") != qc:
			updates["quality_check"] = qc
		if data.get("quality_test"):
			updates["quality_test"] = data.get("quality_test")
		if data.get("slno_of_qc"):
			updates["slno_of_qc"] = data.get("slno_of_qc")

		doc.save(ignore_permissions=True)
		if updates:
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				row.name,
				updates,
				update_modified=False,
			)

	frappe.db.commit()
