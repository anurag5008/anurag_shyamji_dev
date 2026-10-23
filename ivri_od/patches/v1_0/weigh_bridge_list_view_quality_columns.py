"""Weigh Bridge Measurement list: TP No, Truck No in TP and Quality Test in; Quality Check SL NO out.

RST No stays the first (title, clickable) column. The ID column is hidden by the list script.
Column switches are saved the way the desk's "Pick Columns" saves them (Property Setter), because
those win over the DocType file.
"""

import json

import frappe
from frappe.desk.doctype.list_view_settings.list_view_settings import set_in_list_view_property

DOCTYPE = "Weigh Bridge Measurement"

LIST_FIELDS = [
	("transit_pass_no", "TP No"),
	("lot_no", "Lot No"),
	("party_name", "Party Name"),
	("truck_no_in_tp", "Truck No in TP"),
	("actual_truck_no", "Actual Truck No"),
	("net_weight", "Net Weight (QT)"),
	("quality_test", "Quality Test"),
	("tp_status", "Status"),
	("date", "Date & Time"),
]
REMOVED = ["quality_check"]


def execute():
	frappe.reload_doc("procurement", "doctype", "weigh_bridge_measurement")
	fields = json.dumps([{"fieldname": fieldname, "label": label} for fieldname, label in LIST_FIELDS])
	if frappe.db.exists("List View Settings", DOCTYPE):
		frappe.db.set_value("List View Settings", DOCTYPE, "fields", fields)
	else:
		frappe.get_doc({"doctype": "List View Settings", "name": DOCTYPE, "fields": fields}).insert(
			ignore_permissions=True
		)
	meta = frappe.get_meta(DOCTYPE)
	for fieldname, _label in LIST_FIELDS:
		set_in_list_view_property(DOCTYPE, meta.get_field(fieldname), "1")
	for fieldname in REMOVED:
		set_in_list_view_property(DOCTYPE, meta.get_field(fieldname), "0")
	frappe.clear_cache(doctype=DOCTYPE)
