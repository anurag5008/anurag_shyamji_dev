# Copyright (c) 2026, Profezzo and contributors
"""DCRO View DC: the District column (district of "on behalf of OSCSC(...)" on the DC PDF, as in
District Master) on rows saved before it was added, read from each row's saved PDF, as new
reads do (portal_sync.add_dc_district); "No District Matched" when it cannot be read.
Record names and keys do not change."""

import json

import frappe

from ivri_od.procurement.portal_sync import DISTRICT_SECTIONS, add_dc_district, build_row_hash


def execute():
	for site, section in DISTRICT_SECTIONS:
		for record in frappe.get_all(
			"Portal Record", filters={"site": site, "section": section}, fields=["name", "row_data"]
		):
			try:
				cells = json.loads(record.row_data or "{}") or {}
			except ValueError:
				continue
			fixed = add_dc_district(site, section, cells, {}, record.name)
			if fixed != cells:
				frappe.db.set_value(
					"Portal Record",
					record.name,
					{"row_data": json.dumps(fixed, ensure_ascii=False), "row_hash": build_row_hash(fixed)},
					update_modified=False,
				)
