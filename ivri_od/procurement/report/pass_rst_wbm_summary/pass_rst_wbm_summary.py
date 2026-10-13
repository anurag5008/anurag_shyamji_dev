# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Pass / RST"),
			"fieldname": "tree_label",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Pass Unique Key"),
			"fieldname": "pass_unique_key",
			"fieldtype": "Link",
			"options": "PPAS Transit Pass",
			"width": 180,
		},
		{
			"label": _("Season"),
			"fieldname": "season",
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"label": _("TP No"),
			"fieldname": "transit_pass_no",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("RST Count"),
			"fieldname": "rst_count",
			"fieldtype": "Int",
			"width": 90,
		},
		{
			"label": _("TP Quantity (QT)"),
			"fieldname": "tp_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{
			"label": _("Total Received (QT)"),
			"fieldname": "total_received",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("TP Completed"),
			"fieldname": "tp_completed",
			"fieldtype": "Data",
			"width": 110,
		},
	]


def get_data(filters):
	grn_by_pass = _build_grn_received_by_pass()
	wbm_by_pass = _build_wbm_by_pass(filters)
	tp_rows = _fetch_transit_passes(filters)

	data: list[dict] = []
	for tp in tp_rows:
		key = (tp.pass_unique_key or tp.name or "").strip()
		if not key:
			continue

		wbms = wbm_by_pass.get(key, [])
		grn = grn_by_pass.get(key) or {}

		tp_qty = flt(tp.quantity) or flt(grn.get("tp_quantity"))
		total_received = flt(grn.get("total_received"))
		if not total_received:
			total_received = sum(flt(w.get("net_weight")) for w in wbms)

		rst_nos = {(w.get("rst_no") or "").strip() for w in wbms if (w.get("rst_no") or "").strip()}
		rst_count = len(rst_nos) if rst_nos else len(wbms)

		tp_completed = _tp_completed_label(tp_qty, total_received, grn.get("tp_completed_flag"))
		if filters.get("tp_completed") == "Yes" and tp_completed != _("Yes"):
			continue
		if filters.get("tp_completed") == "No" and tp_completed != _("No"):
			continue

		data.append(
			{
				"tree_label": key,
				"pass_unique_key": key,
				"season": (tp.season or "").strip(),
				"transit_pass_no": tp.transit_pass_no,
				"rst_count": rst_count,
				"tp_quantity": tp_qty,
				"total_received": total_received,
				"tp_completed": tp_completed,
				"indent": 0,
			}
		)

		for w in sorted(wbms, key=_wbm_sort_key):
			rst = (w.get("rst_no") or "").strip()
			data.append(
				{
					"tree_label": rst or w.get("name"),
					"pass_unique_key": "",
					"season": "",
					"transit_pass_no": "",
					"rst_count": None,
					"tp_quantity": None,
					"total_received": None,
					"tp_completed": "",
					"indent": 1,
				}
			)

	return data


def _tp_completed_label(tp_qty: float, total_received: float, grn_completed_flag: int | None) -> str:
	if grn_completed_flag:
		return _("Yes")
	if tp_qty > 0 and total_received >= tp_qty:
		return _("Yes")
	return _("No")


def _wbm_sort_key(row: dict) -> tuple:
	return (
		row.get("measurement_date") or "",
		str(row.get("measurement_time") or ""),
		row.get("name") or "",
	)


def _fetch_transit_passes(filters):
	tp_filters: dict = {}
	if filters.get("season"):
		season_label = frappe.db.get_value("Season Master", filters.season, "name") or filters.season
		tp_filters["season"] = season_label
	if filters.get("pass_unique_key"):
		tp_filters["pass_unique_key"] = filters.pass_unique_key

	return frappe.get_all(
		"PPAS Transit Pass",
		filters=tp_filters or None,
		fields=["name", "pass_unique_key", "season", "transit_pass_no", "quantity"],
		order_by="season asc, transit_pass_no asc, pass_unique_key asc",
	)


def _build_grn_received_by_pass() -> dict[str, dict]:
	rows = frappe.db.sql(
		"""
		SELECT
			pass_unique_key,
			SUM(received_quantity) AS total_received,
			MAX(tp_quantity) AS tp_quantity,
			MAX(
				CASE WHEN tp_fulfillment_status = 'TP Completed' THEN 1 ELSE 0 END
			) AS tp_completed_flag
		FROM `tabGRN Note`
		WHERE is_local_procurement = 0
			AND docstatus < 2
			AND IFNULL(pass_unique_key, '') != ''
		GROUP BY pass_unique_key
		""",
		as_dict=True,
	)
	return {row.pass_unique_key: row for row in rows if row.pass_unique_key}


def _build_wbm_by_pass(filters) -> dict[str, list[dict]]:
	conditions = ["IFNULL(w.pass_unique_key, '') != ''"]
	values: list = []

	if filters.get("pass_unique_key"):
		conditions.append("w.pass_unique_key = %s")
		values.append(filters.pass_unique_key)
	if filters.get("from_date"):
		conditions.append("w.measurement_date >= %s")
		values.append(getdate(filters.from_date))
	if filters.get("to_date"):
		conditions.append("w.measurement_date <= %s")
		values.append(getdate(filters.to_date))

	where_sql = " AND ".join(conditions)
	rows = frappe.db.sql(
		f"""
		SELECT
			w.name,
			w.pass_unique_key,
			w.rst_no,
			w.net_weight,
			w.quality_test,
			w.measurement_date,
			w.measurement_time
		FROM `tabWeigh Bridge Measurement` w
		WHERE {where_sql}
		ORDER BY w.pass_unique_key ASC, w.measurement_date ASC, w.measurement_time ASC, w.name ASC
		""",
		tuple(values),
		as_dict=True,
	)

	out: dict[str, list[dict]] = defaultdict(list)
	for row in rows:
		key = (row.pass_unique_key or "").strip()
		if key:
			out[key].append(row)
	return out
