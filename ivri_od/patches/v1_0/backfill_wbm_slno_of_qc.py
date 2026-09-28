"""Backfill Sl No of QC on Weigh Bridge Measurement from open Quality Check."""

import frappe
from frappe.utils import cint

from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	get_effective_truck_no,
	get_qc_serial_for_vehicle,
)


def execute():
	if not frappe.db.has_column("Weigh Bridge Measurement", "slno_of_qc"):
		return

	for row in frappe.get_all(
		"Weigh Bridge Measurement",
		fields=["name", "actual_truck_no", "truck_no_in_tp", "slno_of_qc"],
	):
		vehicle = get_effective_truck_no(row)
		if not vehicle:
			continue
		serial = cint(get_qc_serial_for_vehicle(vehicle) or 0)
		if serial and serial != cint(row.slno_of_qc):
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				row.name,
				"slno_of_qc",
				serial,
				update_modified=False,
			)

	frappe.db.commit()
