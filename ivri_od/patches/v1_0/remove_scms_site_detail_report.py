# Copyright (c) 2026, Profezzo and contributors

import frappe


def execute():
	"""SCMS Site Detail was renamed to Tracking DC Fulfillment (Rice Handover Reports)."""
	if frappe.db.exists("Report", "SCMS Site Detail"):
		frappe.delete_doc("Report", "SCMS Site Detail", force=True, ignore_permissions=True)
