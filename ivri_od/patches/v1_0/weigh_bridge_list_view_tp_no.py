"""Weigh Bridge Measurement list: show TP No before Lot No, in the agreed column order.

RST No is the first (title) column. Rice Dispatch keeps its number in Lot No; TP No stays blank
for it because no Transit Pass is linked.
"""

import json

import frappe

DOCTYPE = "Weigh Bridge Measurement"

LIST_FIELDS = [
	("date", "Date & Time"),
	("transit_pass_no", "TP No"),
	("lot_no", "Lot No"),
	("net_weight", "Net Weight (QT)"),
	("party_name", "Party Name"),
	("quality_check", "Quality Check SL NO"),
	("tp_status", "Status"),
	("quality_test", "Quality Test"),
	("truck_no_in_tp", "Truck No in TP"),
]


def execute():
	frappe.reload_doc("procurement", "doctype", "weigh_bridge_measurement")
	fields = json.dumps([{"fieldname": fieldname, "label": label} for fieldname, label in LIST_FIELDS])
	if frappe.db.exists("List View Settings", DOCTYPE):
		frappe.db.set_value("List View Settings", DOCTYPE, "fields", fields)
	else:
		frappe.get_doc({"doctype": "List View Settings", "name": DOCTYPE, "fields": fields}).insert(
			ignore_permissions=True
		)
	frappe.clear_cache(doctype=DOCTYPE)
