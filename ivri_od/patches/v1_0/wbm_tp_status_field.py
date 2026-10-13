"""Add TP Status on Weigh Bridge Measurement and backfill from RST / pass link."""

import frappe

from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	compute_wbm_tp_status,
)


def execute():
	frappe.reload_doc("procurement", "doctype", "weigh_bridge_measurement")

	for name in frappe.get_all("Weigh Bridge Measurement", pluck="name"):
		doc = frappe.get_doc("Weigh Bridge Measurement", name)
		status = compute_wbm_tp_status(doc)
		if status and (doc.tp_status or "") != status:
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				name,
				"tp_status",
				status,
				update_modified=False,
			)
