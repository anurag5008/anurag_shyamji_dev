# Copyright (c) 2026, Profezzo and contributors
"""Portal Data Extraction "Mill No." (required from now on): filled on the saved
extractions from the mill the agent read ("Mill ID on Portal") when it is in Mill
Master. The others are asked for their Mill No. the next time they are saved."""

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "portal_data_extraction")
	mills = {name.upper(): name for name in frappe.get_all("Mill Master", pluck="name")}
	for doc in frappe.get_all(
		"Portal Data Extraction", filters={"mill": ["in", ["", None]]}, fields=["name", "mill_id"]
	):
		mill = mills.get((doc.mill_id or "").strip().upper())
		if mill:
			frappe.db.set_value("Portal Data Extraction", doc.name, "mill", mill, update_modified=False)
