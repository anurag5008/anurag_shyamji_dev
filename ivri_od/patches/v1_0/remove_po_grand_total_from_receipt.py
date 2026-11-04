# Copyright (c) 2026, Profezzo and contributors
"""Purchase Receipt: remove the Custom Field "PO Grand Total (Decided Deal)".

Only this one Custom Field is removed; no other record is touched."""

import frappe

FIELD = "Purchase Receipt-po_grand_total"


def execute():
	if frappe.db.exists("Custom Field", FIELD):
		frappe.delete_doc("Custom Field", FIELD, force=True, ignore_permissions=True)
	frappe.clear_cache(doctype="Purchase Receipt")
