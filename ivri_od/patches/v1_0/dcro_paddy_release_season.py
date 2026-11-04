# Copyright (c) 2026, Profezzo and contributors
"""DCRO Paddy Release: the page's Season (Kharif / Rabi, element id ddlseason) is saved as a
"Season" column of every row; the Remaining Balance runs per season. Added to the section's
Page Filter Columns unless a Season line is already there."""

import frappe


def execute():
	for name in frappe.get_all(
		"Portal Site Section", filters={"parent": "DCRO", "section_name": "Paddy Release"}, pluck="name"
	):
		current = (frappe.db.get_value("Portal Site Section", name, "filter_columns") or "").strip()
		if "#ddlseason" in current.lower() or any(
			line.split("=")[0].strip().lower() == "season" for line in current.splitlines()
		):
			continue
		value = "\n".join(line for line in (current, "Season = #ddlseason") if line)
		frappe.db.set_value("Portal Site Section", name, "filter_columns", value, update_modified=False)
	frappe.clear_document_cache("Portal Site", "DCRO")
