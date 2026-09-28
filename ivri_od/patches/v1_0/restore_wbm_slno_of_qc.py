"""Restore Sl No of QC on Weigh Bridge Measurement form and backfill values."""

import frappe
from frappe.utils import cint

from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	get_effective_truck_no,
	get_quality_check_for_wbm,
)


def execute():
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_measurement")

	if not frappe.db.has_column("Weigh Bridge Measurement", "slno_of_qc"):
		return

	for row in frappe.get_all(
		"Weigh Bridge Measurement",
		fields=["name", "actual_truck_no", "truck_no_in_tp", "quality_check", "slno_of_qc"],
	):
		data = get_quality_check_for_wbm(
			actual_truck_no=row.actual_truck_no,
			truck_no_in_tp=row.truck_no_in_tp,
		)
		updates = {}
		qc = (data.get("quality_check") or "").strip()
		slno = cint(data.get("slno_of_qc"))
		if qc and (row.quality_check or "") != qc:
			updates["quality_check"] = qc
		if slno != cint(row.slno_of_qc):
			updates["slno_of_qc"] = slno
		if data.get("quality_test") and row.name:
			current_test = frappe.db.get_value("Weigh Bridge Measurement", row.name, "quality_test")
			if (current_test or "") != (data.get("quality_test") or ""):
				updates["quality_test"] = data.get("quality_test")

		if updates:
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				row.name,
				updates,
				update_modified=False,
			)

	frappe.db.commit()
