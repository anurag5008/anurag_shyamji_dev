"""GRN mill/chhatni and Target Allocation / Season Mapping chhatni fields."""

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "grn_note")
	_backfill_grn_mill_name_from_transit_pass()
	frappe.clear_cache()


def _backfill_grn_mill_name_from_transit_pass():
	from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name

	rows = frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2], "is_local_procurement": 0},
		fields=["name", "pass_unique_key", "mill_name"],
	)
	for row in rows:
		key = (row.pass_unique_key or "").strip()
		if not key:
			continue
		miller = frappe.db.get_value("PPAS Transit Pass", {"pass_unique_key": key}, "miller")
		display = (miller or "").strip()
		if not display:
			display = resolve_mill_master_name(key, miller) or ""
		if display and display != (row.mill_name or "").strip():
			frappe.db.set_value("GRN Note", row.name, "mill_name", display, update_modified=False)
