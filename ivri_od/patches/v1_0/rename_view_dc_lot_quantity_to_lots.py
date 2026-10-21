"""DCRO View DC: the value read from td[4] of grdDepotFCIbody / grdDepotRRCbody is the
number of lots, not a quantity. Detail rows saved as "Lot Quantity (Qtl)" become "Lots"."""

import json

import frappe

from ivri_od.procurement.portal_sync import build_details_hash

OLD = "Lot Quantity (Qtl)"
NEW = "Lots"


def execute():
	records = frappe.get_all("Portal Record", filters={"site": "DCRO", "section": "View DC"}, pluck="name")
	for name in records:
		changed = False
		details = []
		for d in frappe.get_all(
			"Portal Record Detail",
			filters={"parenttype": "Portal Record", "parent": name},
			fields=["name", "detail_data"],
			order_by="line_no asc",
		):
			data = json.loads(d.detail_data or "{}")
			if OLD in data:
				data = {(NEW if k == OLD else k): v for k, v in data.items()}
				frappe.db.set_value(
					"Portal Record Detail", d.name, "detail_data", json.dumps(data, ensure_ascii=False),
					update_modified=False,
				)
				changed = True
			details.append(data)
		footer_raw = frappe.db.get_value("Portal Record", name, "details_footer") or "[]"
		footer = [{(NEW if k == OLD else k): v for k, v in f.items()} for f in json.loads(footer_raw)]
		if changed or footer_raw != json.dumps(footer, ensure_ascii=False):
			frappe.db.set_value(
				"Portal Record",
				name,
				{"details_footer": json.dumps(footer, ensure_ascii=False), "details_hash": build_details_hash(details + footer)},
				update_modified=False,
			)
