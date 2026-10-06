"""Net paddy = gross − gunny − deduction, then recompute GRN chhatni from received − TP."""

import frappe
from frappe.utils import flt

from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabWeigh Bridge Measurement`
		SET net_weight = GREATEST(
			IFNULL(gross_weight, 0) - IFNULL(gunny_weight, 0) - IFNULL(deduction, 0),
			0
		)
		WHERE IFNULL(quality_test, '') != 'Rejected'
			AND (
				IFNULL(gross_weight, 0) > 0
				OR IFNULL(gunny_weight, 0) > 0
				OR IFNULL(deduction, 0) > 0
			)
		"""
	)

	keys: set[str] = set()
	for row in frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2]},
		fields=["name", "weigh_bridge_measurement", "pass_unique_key", "is_local_procurement"],
	):
		wbm_name = (row.weigh_bridge_measurement or "").strip()
		if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
			net = flt(frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "net_weight"))
			frappe.db.set_value("GRN Note", row.name, "net_weight", net, update_modified=False)
		key = (row.pass_unique_key or "").strip()
		if key and not row.is_local_procurement:
			keys.add(key)

	for key in keys:
		refresh_tp_fulfillment_for_pass(key)
