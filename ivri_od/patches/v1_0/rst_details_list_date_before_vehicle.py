"""RST Details list: the Date & Time column comes before the Vehicle No column.

The column order is kept in the List View Settings of the DocType (the form layout is not touched)."""

import json

import frappe

DOCTYPE = "RST Details"
ORDER = ["entry_datetime", "vehicle_no", "party_name", "tp_no", "tp_status"]


def execute():
	meta = frappe.get_meta(DOCTYPE)
	fields = [{"fieldname": name, "label": meta.get_label(name)} for name in ORDER]
	if frappe.db.exists("List View Settings", DOCTYPE):
		settings = frappe.get_doc("List View Settings", DOCTYPE)
		current = [f.get("fieldname") for f in json.loads(settings.fields or "[]")]
		# Keep any other column already picked; only put Date & Time first.
		extra = [{"fieldname": n, "label": meta.get_label(n)} for n in current if n and n not in ORDER]
		settings.fields = json.dumps(fields + extra)
		settings.save(ignore_permissions=True)
	else:
		settings = frappe.new_doc("List View Settings")
		settings.name = DOCTYPE
		settings.fields = json.dumps(fields)
		settings.insert(ignore_permissions=True)
	frappe.clear_cache(doctype=DOCTYPE)
