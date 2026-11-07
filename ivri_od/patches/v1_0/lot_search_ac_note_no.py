# Copyright (c) 2026, Profezzo and contributors
"""Lot Search from SCMS: fill the A.C. Note No column (and the Vehicle No) of the saved lots from their Print PDF.

New reads fill them by themselves (portal_sync.add_lot_vehicle); this does the lots already saved. Safe to run again."""

import json

import frappe

from ivri_od.procurement.portal_sync import (
	LOT_AC_NOTE_COLUMN,
	VEHICLE_COLUMN,
	_lot_ac_note_in,
	_saved_file,
	_vehicles_in,
	ac_note_text,
	build_row_hash,
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
		text = ac_note_text(_saved_file(record.receipt_file)) if record.receipt_file else ""
		vehicle = _vehicles_in(text) or cells.get(VEHICLE_COLUMN, "")
		ac_note = _lot_ac_note_in(text) or cells.get(LOT_AC_NOTE_COLUMN, "")
		new_cells = with_vehicle(cells, vehicle, ac_note)
		if list(new_cells.items()) == list(cells.items()):
			continue
		frappe.db.set_value(
			"Portal Record",
			record.name,
			{"row_data": json.dumps(new_cells, ensure_ascii=False), "row_hash": build_row_hash(new_cells)},
			update_modified=False,
		)
