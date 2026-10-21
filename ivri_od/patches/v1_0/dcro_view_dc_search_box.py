# Copyright (c) 2026, Profezzo and contributors
"""DCRO View DC: the read also starts when a value is typed in the table's Search
box (tabledata_filter) and Enter is pressed, as on DC Transit Challan; Show still works."""

import frappe


def execute():
	for name in frappe.get_all(
		"Portal Site Section", filters={"parent": "DCRO", "page_match": "ViewDC"}, pluck="name"
	):
		frappe.db.set_value(
			"Portal Site Section",
			name,
			{"extract_on_click": "Show, tabledata_filter", "extract_only_on_click": 1},
			update_modified=False,
		)
