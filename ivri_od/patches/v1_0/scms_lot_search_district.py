# Copyright (c) 2026, Profezzo and contributors
"""SCMS Lot Search: the page's District (element id ddlDistrict) is saved as a "District" column
of every row. Added to the section's Page Filter Columns unless a District line is already there."""

import frappe


def execute():
	for name in frappe.get_all(
		"Portal Site Section", filters={"parent": "SCMS", "section_name": "Lot Search"}, pluck="name"
	):
		current = (frappe.db.get_value("Portal Site Section", name, "filter_columns") or "").strip()
		if "#ddldistrict" in current.lower() or any(
			line.split("=")[0].strip().lower() == "district" for line in current.splitlines()
		):
			continue
		value = "\n".join(line for line in (current, "District = #ddlDistrict") if line)
		frappe.db.set_value("Portal Site Section", name, "filter_columns", value, update_modified=False)
	frappe.clear_document_cache("Portal Site", "SCMS")
