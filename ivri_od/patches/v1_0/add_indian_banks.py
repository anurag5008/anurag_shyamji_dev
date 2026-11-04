# Copyright (c) 2026, Profezzo and contributors
"""Bank: add the banks of India, and the local banks of Odisha, to the Bank list (for the Mark as completed form of Mill Reminder).

Only banks that are not already in the list are added; nothing that exists is changed."""

import frappe

from ivri_od.procurement.bank_list import all_banks


def execute():
	for name in all_banks():
		if not frappe.db.exists("Bank", name):
			frappe.get_doc({"doctype": "Bank", "bank_name": name}).insert(ignore_permissions=True)
