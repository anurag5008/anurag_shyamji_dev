"""Weigh Bridge Measurement list: the agreed column set and order.

RST No stays the first (title, clickable) column. Then: Transit Pass No, Lot No, Party Name,
Actual Truck No, Net Weight (QT), Quality Check SL NO, Status, Date & Time.
Quality Test and Truck No in TP leave the default list (still available in Pick Columns).
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
	("actual_truck_no", "Actual Truck No"),
	("net_weight", "Net Weight (QT)"),
	("quality_check", "Quality Check SL NO"),
	("tp_status", "Status"),
	("date", "Date & Time"),
]
REMOVED = ["quality_test", "truck_no_in_tp"]


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
