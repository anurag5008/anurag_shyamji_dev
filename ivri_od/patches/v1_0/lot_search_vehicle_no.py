# Copyright (c) 2026, Profezzo and contributors
"""Lot Search from SCMS: fill the Vehicle No column of the saved lots from their Print PDF (Vehicle Registration No.).

New reads fill it by themselves (portal_sync.add_lot_vehicle); this does the lots already saved. Safe to run again."""

import json

import frappe

from ivri_od.procurement.portal_sync import (
	VEHICLE_COLUMN,
	_saved_file,
	build_row_hash,
	lot_vehicle_numbers,
	with_vehicle,
)


def execute():
	for record in frappe.get_all(
		"Portal Record",
		filters={"site": "SCMS", "section": "Lot Search"},
		fields=["name", "receipt_file", "row_data"],
		limit_page_length=0,
	):
		try:
			cells = json.loads(record.row_data or "{}") or {}
		except ValueError:
			continue
		vehicle = lot_vehicle_numbers(_saved_file(record.receipt_file)) or cells.get(VEHICLE_COLUMN, "")
		new_cells = with_vehicle(cells, vehicle)
		if new_cells == cells and list(new_cells) == list(cells):
			continue
		frappe.db.set_value(
			"Portal Record",
			record.name,
			{"row_data": json.dumps(new_cells, ensure_ascii=False), "row_hash": build_row_hash(new_cells)},
			update_modified=False,
		)
