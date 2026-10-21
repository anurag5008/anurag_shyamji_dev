# Copyright (c) 2026, Profezzo and contributors

import frappe

# Old report name -> new name (the new reports are installed by procurement_reports.py).
RENAMED = {
	"Tracking DC Fulfillment": "RRC DC Summary from SCMS",
	"Tracking Transit Challan": "RRC Transit Pass from SCMS",
}


def execute():
	"""SCMS reports were renamed; remove the old Report records so menus show only the new names."""
	for old in RENAMED:
		if frappe.db.exists("Report", old):
			frappe.delete_doc("Report", old, force=True, ignore_permissions=True)
