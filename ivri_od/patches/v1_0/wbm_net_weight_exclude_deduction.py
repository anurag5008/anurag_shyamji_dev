"""Net paddy = gross − gunny only; deduction is for chhatni % only."""

import frappe
from frappe.utils import flt

from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabWeigh Bridge Measurement`
		SET net_weight = GREATEST(IFNULL(gross_weight, 0) - IFNULL(gunny_weight, 0), 0)
		WHERE IFNULL(gross_weight, 0) > 0 OR IFNULL(gunny_weight, 0) > 0
		"""
	)

	keys = frappe.db.sql(
		"""
		SELECT DISTINCT pass_unique_key
		FROM `tabWeigh Bridge Measurement`
		WHERE is_farmer_or_agent = 0 AND IFNULL(pass_unique_key, '') != ''
		""",
		pluck=True,
	)
	for key in keys:
		refresh_tp_fulfillment_for_pass(key)

	# Resync GRN net from WBM where linked
	for row in frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2], "is_local_procurement": 0},
		fields=["name", "weigh_bridge_measurement", "pass_unique_key"],
	):
		wbm_name = (row.weigh_bridge_measurement or "").strip()
		if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
			continue
		net = flt(frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "net_weight"))
		frappe.db.set_value("GRN Note", row.name, "net_weight", net, update_modified=False)
		if row.pass_unique_key:
			refresh_tp_fulfillment_for_pass(row.pass_unique_key)
