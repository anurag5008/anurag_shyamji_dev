# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import json

import frappe


def sync_saved_field_order(doc, method=None):
	"""Copy a DocType save into the Customize Form field order.

	The field_order Property Setter is what the form actually renders. If it
	still lists an older, partial order, fields the user just moved snap back.
	"""
	if (
		frappe.flags.in_import
		or frappe.flags.in_migrate
		or frappe.flags.in_install
		or frappe.flags.in_patch
	):
		return

	order = [df.fieldname for df in (doc.fields or []) if df.fieldname]
	if not order:
		return

	existing = frappe.db.get_value(
		"Property Setter",
		{"doc_type": doc.name, "property": "field_order", "doctype_or_field": "DocType"},
		["name", "value"],
		as_dict=True,
	)
	if not existing:
		return

	new_value = json.dumps(order)
	if existing.value == new_value:
		return

	frappe.db.set_value("Property Setter", existing.name, "value", new_value, update_modified=True)
	frappe.clear_cache(doctype=doc.name)
