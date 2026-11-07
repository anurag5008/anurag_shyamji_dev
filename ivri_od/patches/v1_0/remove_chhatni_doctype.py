# Copyright (c) 2026, Profezzo and contributors
"""Remove the Chhatni doc from the system: it is not used any more.

Chhatni now comes from the Mandi Book (Total Qty Received - TP Qty - Excess Received Qty). Chhatni Assign and
Chhatni Excess stay. The records of the doc and its table are deleted."""

import frappe


def execute():
	if frappe.db.exists("DocType", "Chhatni"):
		frappe.delete_doc("DocType", "Chhatni", force=True, ignore_missing=True)
	frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabChhatni`")
	for table, filters in (
		("Workspace Link", {"link_to": "Chhatni"}),
		("Workspace Sidebar Item", {"link_to": "Chhatni"}),
		("Workspace Shortcut", {"link_to": "Chhatni"}),
	):
		if frappe.db.table_exists(table):
			frappe.db.delete(table, filters)
	frappe.clear_cache()
