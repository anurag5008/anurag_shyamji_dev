"""Rename report Chhatni TP Tracking → Chhatni Tracking."""

import frappe


OLD_NAME = "Chhatni TP Tracking"
NEW_NAME = "Chhatni Tracking"


def execute():
	if frappe.db.exists("Report", OLD_NAME) and not frappe.db.exists("Report", NEW_NAME):
		frappe.rename_doc("Report", OLD_NAME, NEW_NAME, force=True, merge=False)
	elif frappe.db.exists("Report", OLD_NAME) and frappe.db.exists("Report", NEW_NAME):
		frappe.delete_doc("Report", OLD_NAME, force=True, ignore_permissions=True)

	frappe.db.set_value("Report", NEW_NAME, "report_name", NEW_NAME, update_modified=False)
