"""Backfill Weigh Bridge Measurement quality_test from linked Quality Check."""

import frappe

from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	get_quality_check_for_wbm,
)


def execute():
	if not frappe.db.has_column("Weigh Bridge Measurement", "quality_test"):
		return

	for row in frappe.get_all(
		"Weigh Bridge Measurement",
		fields=["name", "actual_truck_no", "truck_no_in_tp", "quality_check", "quality_test"],
	):
		data = get_quality_check_for_wbm(
			actual_truck_no=row.actual_truck_no,
			truck_no_in_tp=row.truck_no_in_tp,
		)
		qc = data.get("quality_check") or ""
		test = data.get("quality_test") or "Pending QC"
		if (row.quality_check or "") == qc and (row.quality_test or "") == test:
			continue
		frappe.db.set_value(
			"Weigh Bridge Measurement",
			row.name,
			{"quality_check": qc, "quality_test": test},
			update_modified=False,
		)

	frappe.db.commit()
