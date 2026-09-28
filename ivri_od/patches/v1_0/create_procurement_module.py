import frappe


def execute():
	"""Ensure Procurement Module Def exists before DocType sync."""
	if not frappe.db.exists("Module Def", "Procurement"):
		frappe.get_doc(
			{
				"doctype": "Module Def",
				"module_name": "Procurement",
				"app_name": "ivri_od",
			}
		).insert(ignore_permissions=True)
