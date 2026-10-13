# Copyright (c) 2026, Profezzo and contributors

import frappe


def execute():
	frappe.db.sql("update `tabDocType` set quick_entry = 0 where quick_entry = 1")
	frappe.clear_cache(doctype="DocType")
