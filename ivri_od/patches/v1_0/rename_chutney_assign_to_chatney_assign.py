"""Rename Chutney Assign to Chatney Assign."""

import frappe


def execute():
	old_name = "Chutney Assign"
	new_name = "Chatney Assign"
	if frappe.db.exists("DocType", old_name) and not frappe.db.exists("DocType", new_name):
		frappe.rename_doc("DocType", old_name, new_name, force=True)
	frappe.clear_cache(doctype=new_name)
