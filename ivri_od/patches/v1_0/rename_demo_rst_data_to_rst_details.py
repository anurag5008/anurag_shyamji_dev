"""Rename the imported RST record DocType without dropping its existing rows."""

import frappe


def execute():
	old_name = "Demo RST Data"
	new_name = "RST Details"
	if frappe.db.exists("DocType", old_name) and not frappe.db.exists("DocType", new_name):
		# The source files were already moved to rst_details. Suppress Frappe's
		# automatic file move while the patch renames the database DocType.
		frappe.flags.in_patch = True
		try:
			frappe.rename_doc("DocType", old_name, new_name, force=True)
		finally:
			frappe.flags.in_patch = False
	frappe.clear_cache(doctype=new_name)
