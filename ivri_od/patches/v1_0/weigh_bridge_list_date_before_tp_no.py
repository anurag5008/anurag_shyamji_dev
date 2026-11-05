"""Weigh Bridge Measurement list: the Date & Time column comes before the TP No column.

The column order is kept in the List View Settings of the DocType. Only that order is changed."""

import json

import frappe

DOCTYPE = "Weigh Bridge Measurement"


def execute():
	if not frappe.db.exists("List View Settings", DOCTYPE):
		return
	settings = frappe.get_doc("List View Settings", DOCTYPE)
	fields = json.loads(settings.fields or "[]")
	names = [f.get("fieldname") for f in fields]
	if "date" not in names or "transit_pass_no" not in names:
		return
	date_field = fields.pop(names.index("date"))
	fields.insert([f.get("fieldname") for f in fields].index("transit_pass_no"), date_field)
	settings.fields = json.dumps(fields)
	settings.save(ignore_permissions=True)
	frappe.clear_cache(doctype=DOCTYPE)
