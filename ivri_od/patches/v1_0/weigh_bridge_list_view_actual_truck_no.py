"""Weigh Bridge Measurement list: add Actual Truck No after Truck No in TP.

The saved column order is kept as it is; only the new column is added. A list setting saved from the
desk (Property Setter) wins over the DocType file, so the column is switched on the same way the
desk's "Pick Columns" does.
"""

import json

import frappe
from frappe.desk.doctype.list_view_settings.list_view_settings import set_in_list_view_property

DOCTYPE = "Weigh Bridge Measurement"
FIELD = {"fieldname": "actual_truck_no", "label": "Actual Truck No"}
AFTER = "truck_no_in_tp"


def execute():
	frappe.reload_doc("procurement", "doctype", "weigh_bridge_measurement")
	_add_to_saved_order()
	set_in_list_view_property(DOCTYPE, frappe.get_meta(DOCTYPE).get_field(FIELD["fieldname"]), "1")
	frappe.clear_cache(doctype=DOCTYPE)


def _add_to_saved_order():
	if not frappe.db.exists("List View Settings", DOCTYPE):
		return
	fields = json.loads(frappe.db.get_value("List View Settings", DOCTYPE, "fields") or "[]")
	names = [field.get("fieldname") for field in fields]
	if not fields or FIELD["fieldname"] in names:
		return
	position = names.index(AFTER) + 1 if AFTER in names else len(fields)
	fields.insert(position, dict(FIELD))
	frappe.db.set_value("List View Settings", DOCTYPE, "fields", json.dumps(fields))
