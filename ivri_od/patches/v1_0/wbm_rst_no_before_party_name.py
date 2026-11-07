# Copyright (c) 2026, Profezzo and contributors
"""Weigh Bridge Measurement: RST No comes before Party Name (form and list filters).

A saved field order (Property Setter) wins over the DocType file, so it is changed here as well."""

import json

import frappe

DOCTYPE = "Weigh Bridge Measurement"


def execute():
	name = frappe.db.get_value("Property Setter", {"doc_type": DOCTYPE, "property": "field_order"}, "name")
	if not name:
		return
	setter = frappe.get_doc("Property Setter", name)
	order = json.loads(setter.value or "[]")
	if "rst_no" in order and "party_name" in order:
		order.remove("rst_no")
		order.insert(order.index("party_name"), "rst_no")
		setter.value = json.dumps(order)
		setter.save(ignore_permissions=True)
	frappe.clear_cache(doctype=DOCTYPE)
