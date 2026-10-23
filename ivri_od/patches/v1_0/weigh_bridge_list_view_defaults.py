"""Weigh Bridge Measurement list: useful default column order and newest-first sorting.

Column order comes from the List View Settings record (the form's field order stays as it is).
An existing List View Settings record is left alone. Saved per-user sort of this list is reset to
the new default so every user sees the same order after a refresh.
"""

import json

import frappe

DOCTYPE = "Weigh Bridge Measurement"

# RST No is the first (title) column; these follow in this order.
LIST_FIELDS = [
	("lot_no", "Lot No"),
	("party_name", "Party Name"),
	("tp_status", "Status"),
	("quality_test", "Quality Test"),
	("net_weight", "Net Weight (QT)"),
	("truck_no_in_tp", "Truck No in TP"),
	("quality_check", "Quality Check SL NO"),
	("date", "Date & Time"),
]


def execute():
	frappe.reload_doc("procurement", "doctype", "weigh_bridge_measurement")
	_set_default_columns()
	_reset_saved_sort()
	frappe.clear_cache(doctype=DOCTYPE)


def _set_default_columns():
	if frappe.db.exists("List View Settings", DOCTYPE):
		return
	frappe.get_doc(
		{
			"doctype": "List View Settings",
			"name": DOCTYPE,
			"fields": json.dumps([{"label": label, "fieldname": fieldname} for fieldname, label in LIST_FIELDS]),
		}
	).insert(ignore_permissions=True)


def _reset_saved_sort():
	for row in frappe.db.sql(
		"select user, data from `__UserSettings` where doctype = %s", (DOCTYPE,), as_dict=True
	):
		try:
			data = json.loads(row.data or "{}")
		except ValueError:
			continue
		view = data.get("List")
		if not isinstance(view, dict):
			continue
		view["sort_by"] = "date"
		view["sort_order"] = "desc"
		frappe.db.sql(
			"update `__UserSettings` set data = %s where user = %s and doctype = %s",
			(json.dumps(data), row.user, DOCTYPE),
		)
