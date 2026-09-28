# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"label": _("Season"),
			"fieldname": "season",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("PPC Name"),
			"fieldname": "ppc_display",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Mandi Qty (Season Mapping)"),
			"fieldname": "mandi_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Pass Unique Key"),
			"fieldname": "pass_unique_key",
			"fieldtype": "Link",
			"options": "PPAS Transit Pass",
			"width": 200,
		},
		{
			"label": _("Transit Pass No"),
			"fieldname": "transit_pass_no",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("TP Quantity"),
			"fieldname": "tp_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"label": _("Fulfilled (WBM Net)"),
			"fieldname": "fulfilled_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("Weigh Bridge Count"),
			"fieldname": "wbm_count",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": _("Remaining TP Qty"),
			"fieldname": "remaining_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
	]


def get_data(filters):
	mandi_map = _build_mandi_quantity_map()
	wbm_map = _build_wbm_aggregates()

	tp_filters: dict = {}
	if filters.get("season"):
		season_label = frappe.db.get_value("Season Master", filters.season, "name") or filters.season
		tp_filters["season"] = season_label

	rows = frappe.get_all(
		"PPAS Transit Pass",
		filters=tp_filters or None,
		fields=[
			"name",
			"pass_unique_key",
			"season",
			"ppc",
			"transit_pass_no",
			"quantity",
		],
		order_by="season asc, ppc asc, transit_pass_no asc",
	)

	data = []
	for tp in rows:
		ppc_link = _resolve_ppc_master_link(tp.ppc)
		if filters.get("ppc_name") and ppc_link != filters.ppc_name:
			continue

		ppc_display = _ppc_display(ppc_link, tp.ppc)
		mandi_qty = _mandi_quantity_for_tp(tp.season, ppc_link, mandi_map)
		key = (tp.pass_unique_key or tp.name or "").strip()
		agg = wbm_map.get(key) or {}
		fulfilled = flt(agg.get("fulfilled_quantity"))
		wbm_count = int(agg.get("wbm_count") or 0)
		tp_qty = flt(tp.quantity)
		remaining = flt(tp_qty - fulfilled)
		if remaining < 0:
			remaining = 0

		data.append(
			{
				"season": (tp.season or "").strip(),
				"ppc_display": ppc_display,
				"mandi_quantity": mandi_qty,
				"pass_unique_key": key,
				"transit_pass_no": tp.transit_pass_no,
				"tp_quantity": tp_qty,
				"fulfilled_quantity": fulfilled,
				"wbm_count": wbm_count,
				"remaining_quantity": remaining,
			}
		)

	return data


def _build_mandi_quantity_map() -> dict[tuple[str, str], float]:
	"""(season_doc_name, ppc_master_name) -> season_quantity."""
	out: dict[tuple[str, str], float] = {}
	for row in frappe.get_all(
		"Season Mapping",
		fields=["season", "ppc_name", "season_quantity"],
	):
		season = (row.season or "").strip()
		ppc = (row.ppc_name or "").strip()
		if not season or not ppc:
			continue
		out[(season, ppc)] = flt(row.season_quantity)
	return out


def _mandi_quantity_for_tp(
	season_text: str | None, ppc_link: str | None, mandi_map: dict[tuple[str, str], float]
) -> float:
	season_text = (season_text or "").strip()
	ppc_link = (ppc_link or "").strip()
	if not season_text or not ppc_link:
		return 0

	season_doc = season_text
	if not frappe.db.exists("Season Master", season_doc):
		season_doc = frappe.db.get_value("Season Master", {"name": season_text}, "name") or season_text

	return flt(mandi_map.get((season_doc, ppc_link)))


def _resolve_ppc_master_link(ppc_text: str | None) -> str | None:
	text = (ppc_text or "").strip()
	if not text:
		return None
	if frappe.db.exists("PPC Master", text):
		return text
	by_name = frappe.db.get_value("PPC Master", {"ppc_name": text}, "name")
	if by_name:
		return by_name
	return frappe.db.get_value("PPC Master", {"code": text}, "name")


def _ppc_display(ppc_link: str | None, fallback: str | None) -> str:
	if ppc_link:
		name = frappe.db.get_value("PPC Master", ppc_link, "ppc_name")
		if name:
			return name.strip()
		return ppc_link
	return (fallback or "").strip()


def _build_wbm_aggregates() -> dict[str, dict]:
	rows = frappe.db.sql(
		"""
		SELECT
			pass_unique_key,
			COUNT(name) AS wbm_count,
			COALESCE(SUM(net_weight), 0) AS fulfilled_quantity
		FROM `tabWeigh Bridge Measurement`
		WHERE IFNULL(pass_unique_key, '') != ''
		GROUP BY pass_unique_key
		""",
		as_dict=True,
	)
	return {row.pass_unique_key: row for row in rows if row.pass_unique_key}
