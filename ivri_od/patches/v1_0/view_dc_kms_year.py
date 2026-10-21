# Copyright (c) 2026, Profezzo and contributors
"""DCRO View DC "KMS (Year)": the season's year (2026) saved as its KMS year (2025-26),
as new reads do (portal_sync.fix_section_cells). Record names and keys do not change."""

import json

import frappe

from ivri_od.procurement.portal_sync import build_row_hash, fix_section_cells


def execute():
	for record in frappe.get_all("Portal Record", filters={"section": "View DC"}, fields=["name", "row_data"]):
		try:
			cells = json.loads(record.row_data or "{}") or {}
		except ValueError:
			continue
		fixed = fix_section_cells("View DC", cells)
		if fixed != cells:
			frappe.db.set_value(
				"Portal Record",
				record.name,
				{"row_data": json.dumps(fixed, ensure_ascii=False), "row_hash": build_row_hash(fixed)},
				update_modified=False,
			)
