# Copyright (c) 2026, Profezzo and contributors
"""DCRO pages with years of rows wait for the user's filter before a read:
- DC Transit Challan: Show only loads the rows; the read starts after a value is
  typed in the table's Search box (gvDCDetails_filter) and Enter is pressed.
- View DC: the read starts on Show, not on the menu click or a row's View button."""

import frappe

SETTINGS = {
	"DCTransitChalanView": "gvDCDetails_filter",
	"ViewDC": "Show",
}


def execute():
	frappe.reload_doc("procurement", "doctype", "portal_site_section")
	for page_match, trigger in SETTINGS.items():
		for name in frappe.get_all(
			"Portal Site Section", filters={"parent": "DCRO", "page_match": page_match}, pluck="name"
		):
			frappe.db.set_value(
				"Portal Site Section",
				name,
				{"extract_on_click": trigger, "extract_only_on_click": 1},
				update_modified=False,
			)
