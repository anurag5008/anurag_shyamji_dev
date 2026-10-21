# Copyright (c) 2026, Profezzo and contributors
"""Portal Record "Mill ID": filled from each saved row's own mill column (e.g. SCMS
"Miller Code", DCRO "MillerCode"). Record names stay as they are; a record saved
without a mill gets its mill on the next read (see portal_sync.resolve_record_name).
Sites with a Mill ID XPath (WINGS) are skipped: their mill comes from the dashboard."""

import json

import frappe

from ivri_od.procurement.portal_sync import mill_label_keys, row_mill_id


def execute():
	frappe.reload_doc("procurement", "doctype", "portal_record")
	frappe.reload_doc("procurement", "doctype", "portal_site")
	keys = {}
	for record in frappe.get_all(
		"Portal Record", filters={"mill_id": ["in", ["", None]]}, fields=["name", "site", "row_data"]
	):
		if record.site not in keys:
			labels, xpath = frappe.db.get_value("Portal Site", record.site, ["mill_id_labels", "mill_id_xpath"]) or ("", "")
			keys[record.site] = None if xpath else mill_label_keys(labels)
		if keys[record.site] is None:
			continue
		try:
			cells = json.loads(record.row_data or "{}") or {}
		except ValueError:
			continue
		mill_id = row_mill_id(cells, keys[record.site])
		if mill_id:
			frappe.db.set_value("Portal Record", record.name, "mill_id", mill_id, update_modified=False)
