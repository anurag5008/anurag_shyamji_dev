"""GRN received = net + deduction; chhatni from the deduction sum."""

import frappe

from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass


def execute():
	keys = frappe.db.sql(
		"""
		SELECT DISTINCT pass_unique_key
		FROM `tabGRN Note`
		WHERE is_local_procurement = 0
			AND docstatus < 2
			AND IFNULL(pass_unique_key, '') != ''
		""",
		pluck=True,
	)
	for key in keys:
		refresh_tp_fulfillment_for_pass(key)
