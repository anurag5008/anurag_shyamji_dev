# Copyright (c) 2026, Profezzo and contributors
"""Weigh Bridge Measurement Party Name = the Party Name of its RST Details.

Weighments of a Transit Pass had no Party Name, so the list could not filter on it. Safe to run again."""

import frappe


def execute():
	party_by_rst = {
		row.name: (row.party_name or "").strip()
		for row in frappe.get_all("RST Details", fields=["name", "party_name"])
	}
	for wbm in frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"demo_rst_data": ["is", "set"]},
		fields=["name", "demo_rst_data", "party_name"],
	):
		party = party_by_rst.get(wbm.demo_rst_data)
		if party and (wbm.party_name or "").strip() != party:
			frappe.db.set_value("Weigh Bridge Measurement", wbm.name, "party_name", party, update_modified=False)
