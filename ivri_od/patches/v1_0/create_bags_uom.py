# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Create the Bags UOM used on Purchase Order items (the UOM dropdown there lists only Bags, Trip and Quintal)."""

import frappe


def execute():
	if not frappe.db.exists("UOM", "Bags"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Bags", "enabled": 1}).insert(ignore_permissions=True)
