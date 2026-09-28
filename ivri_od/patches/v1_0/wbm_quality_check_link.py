"""Link Weigh Bridge Measurement to Quality Check document ID."""

import frappe

from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	get_effective_truck_no,
	get_quality_check_for_vehicle,
)
from ivri_od.patches.v1_0.reload_quality_check_doctype import execute as reload_doctypes


def execute():
	reload_doctypes()

	if not frappe.db.has_column("Weigh Bridge Measurement", "quality_check"):
		return

	for row in frappe.get_all(
		"Weigh Bridge Measurement",
		fields=["name", "actual_truck_no", "truck_no_in_tp", "quality_check"],
	):
		if row.quality_check:
			continue
		vehicle = get_effective_truck_no(row)
		if not vehicle:
			continue
		qc_name = get_quality_check_for_vehicle(vehicle)
		if qc_name:
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				row.name,
				"quality_check",
				qc_name,
				update_modified=False,
			)

	frappe.db.commit()
