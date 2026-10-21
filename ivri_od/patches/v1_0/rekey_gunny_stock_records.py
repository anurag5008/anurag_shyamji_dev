"""Gunny Stock Register Details: one record per date (key "Date - A").

The section had no key, so a record was the whole row and every changed day
(or the "Total" line) became a new record. Set the key (the fixture sets it
too, but patches run before fixtures) and re-key the saved records; for a date
saved more than once, the latest read is kept."""

import frappe

from ivri_od.procurement.portal_sync import (
	build_record_key,
	build_record_name,
	build_summary,
	parse_key_columns,
)

SITE = "SCMS"
SECTION = "Gunny Stock Register Details"
KEY = "Date - A"


def execute():
	if not frappe.db.exists("Portal Site", SITE):
		return
	site = frappe.get_doc("Portal Site", SITE)
	section = site.get_section(SECTION)
	if not section:
		return
	if not section.key_columns:
		section.key_columns = KEY
		site.save(ignore_permissions=True)
	key_columns = parse_key_columns(section.key_columns)

	records = frappe.get_all(
		"Portal Record",
		filters={"site": SITE, "section": SECTION},
		fields=["name", "row_data"],
		order_by="last_seen_on desc, seen_run desc",
	)
	kept = set()
	for record in records:
		cells = frappe.parse_json(record.row_data or "{}") or {}
		record_key = build_record_key(cells, key_columns)
		new_name = build_record_name(SITE, SECTION, record_key)
		if new_name in kept:
			frappe.delete_doc("Portal Record", record.name, ignore_permissions=True, force=True)
			continue
		kept.add(new_name)
		if new_name != record.name:
			frappe.rename_doc("Portal Record", record.name, new_name, force=True, show_alert=False)
		frappe.db.set_value(
			"Portal Record",
			new_name,
			{"record_key": record_key, "summary": build_summary(cells, key_columns)},
			update_modified=False,
		)
