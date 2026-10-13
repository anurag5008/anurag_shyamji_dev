"""Recalculate GRN TP/Chhatni status (overfill rule and TP-not-filled chhatni note)."""

import frappe

from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass


def execute():
	keys = frappe.get_all(
		"GRN Note",
		filters={"is_local_procurement": 0, "docstatus": ["<", 2]},
		pluck="pass_unique_key",
	)
	seen = set()
	for key in keys:
		key = (key or "").strip()
		if not key or key in seen:
			continue
		seen.add(key)
		refresh_tp_fulfillment_for_pass(key)
	frappe.clear_cache()
