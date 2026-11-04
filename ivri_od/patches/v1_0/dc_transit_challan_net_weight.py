# Copyright (c) 2026, Profezzo and contributors
"""DCRO DC Transit Challan: the Net Weight column on rows saved before it was added,
read from each row's saved AC Note, as new reads do (portal_sync.add_net_weight).
Record names and keys do not change. "If FCI AC Not Available" gets its Net Quantity (287.5)."""

import json

import frappe

from ivri_od.procurement.portal_sync import (
	DEFAULT_NET_QUANTITY,
	NET_WEIGHT_MASTER,
	NET_WEIGHT_SECTIONS,
	add_net_weight,
	build_row_hash,
)


def execute():
	if not frappe.db.get_single_value(NET_WEIGHT_MASTER, "net_quantity"):
		frappe.db.set_single_value(NET_WEIGHT_MASTER, "net_quantity", DEFAULT_NET_QUANTITY)
	for site, section in NET_WEIGHT_SECTIONS:
		for record in frappe.get_all(
			"Portal Record", filters={"site": site, "section": section}, fields=["name", "row_data"]
		):
			try:
				cells = json.loads(record.row_data or "{}") or {}
			except ValueError:
				continue
			fixed = add_net_weight(site, section, cells, {}, record.name)
			if fixed != cells:
				frappe.db.set_value(
					"Portal Record",
					record.name,
					{"row_data": json.dumps(fixed, ensure_ascii=False), "row_hash": build_row_hash(fixed)},
					update_modified=False,
				)
