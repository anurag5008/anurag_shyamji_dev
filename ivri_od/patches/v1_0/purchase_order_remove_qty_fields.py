# Copyright (c) 2026, Profezzo and contributors
"""Purchase Order: remove the QTL, Bags and Trips Custom Fields added earlier.

Quantity is entered in the Items table. Only these three Custom Fields are removed; no other record is touched."""

import frappe

FIELDS = ["Purchase Order-qtl", "Purchase Order-bags", "Purchase Order-trips"]


def execute():
	for name in FIELDS:
		if frappe.db.exists("Custom Field", name):
			frappe.delete_doc("Custom Field", name, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="Purchase Order")
