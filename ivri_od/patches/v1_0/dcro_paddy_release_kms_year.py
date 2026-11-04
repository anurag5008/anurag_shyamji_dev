# Copyright (c) 2026, Profezzo and contributors
"""DCRO Paddy Release: the page's KMS Year (element id INTKMS) is saved as a "KMS Year"
column of every row. A section whose Page Filter Columns were already set is kept."""

import frappe


def execute():
	for name in frappe.get_all(
		"Portal Site Section", filters={"parent": "DCRO", "section_name": "Paddy Release"}, pluck="name"
	):
		if not (frappe.db.get_value("Portal Site Section", name, "filter_columns") or "").strip():
			frappe.db.set_value(
				"Portal Site Section", name, "filter_columns", "KMS Year = #INTKMS", update_modified=False
			)
	frappe.clear_document_cache("Portal Site", "DCRO")
