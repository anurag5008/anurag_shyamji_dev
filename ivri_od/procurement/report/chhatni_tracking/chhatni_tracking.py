# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.doctype.target_allocation.target_allocation import (
	get_latest_chutney_for_ppc_mill,
)
from ivri_od.procurement.grn_tp_fulfillment import (
	chhatni_fulfillment_status,
	received_chhatni_pct,
)
from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name, resolve_ppc_master_name


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Season"), "fieldname": "season", "fieldtype": "Data", "width": 110},
		{"label": _("PPC Name"), "fieldname": "ppc_display", "fieldtype": "Data", "width": 150},
		{"label": _("Mill"), "fieldname": "mill_display", "fieldtype": "Data", "width": 120},
		{"label": _("Transit Pass No"), "fieldname": "transit_pass_no", "fieldtype": "Data", "width": 110},
		{
			"label": _("Pass Unique Key"),
			"fieldname": "pass_unique_key",
			"fieldtype": "Link",
			"options": "PPAS Transit Pass",
			"width": 200,
		},
		{
			"label": _("Chhatni Assigned (Kg/Qt)"),
			"fieldname": "chhatni_assigned_kg",
			"fieldtype": "Float",
			"precision": 2,
			"width": 130,
		},
		{
			"label": _("Chhatni Assigned %"),
			"fieldname": "chhatni_assigned_pct",
			"fieldtype": "Percent",
			"precision": 2,
			"width": 120,
		},
		{
			"label": _("TP Quantity (QT)"),
			"fieldname": "tp_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"label": _("Total Received (QT)"),
			"fieldname": "total_received",
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{
			"label": _("TP Fully Received"),
			"fieldname": "tp_filled",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Received Chhatni %"),
			"fieldname": "received_chhatni_pct",
			"fieldtype": "Percent",
			"precision": 2,
			"width": 120,
		},
		{
			"label": _("Chhatni Status"),
			"fieldname": "chhatni_status",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Received − TP Qty (QT)"),
			"fieldname": "received_minus_tp",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("Chhatni Assign"),
			"fieldname": "chhatni_assign",
			"fieldtype": "Link",
			"options": "Chhatni Assign",
			"width": 120,
		},
	]


def get_data(filters):
	grn_map = _build_grn_summary_by_pass()
	tp_rows = frappe.get_all(
		"PPAS Transit Pass",
		fields=[
			"name",
			"pass_unique_key",
			"season",
			"ppc",
			"miller",
			"transit_pass_no",
			"quantity",
		],
		order_by="season asc, ppc asc, transit_pass_no asc",
	)

	data = []
	for tp in tp_rows:
		if filters.get("transit_pass_no"):
			if (tp.transit_pass_no or "").strip() != (filters.transit_pass_no or "").strip():
				continue

		season_master = resolve_season_master_name(tp.season) or (tp.season or "").strip()
		if filters.get("season") and season_master != filters.season:
			continue

		ppc_link = resolve_ppc_master_name(tp.ppc) or (tp.ppc or "").strip()
		if filters.get("ppc_name") and ppc_link != filters.ppc_name:
			continue

		pass_key = (tp.pass_unique_key or tp.name or "").strip()
		mill_link = resolve_mill_master_name(pass_key, tp.miller) or ""
		if filters.get("mill_name") and mill_link != filters.mill_name:
			continue

		tp_qty = flt(tp.quantity)
		grn = grn_map.get(pass_key) or {}
		total_received = flt(grn.get("total_received"))
		if not total_received and tp_qty:
			total_received = flt(grn.get("sum_received"))

		chhatni_row = get_latest_chutney_for_ppc_mill(ppc_link, mill_link, season_master)
		# Rate frozen on GRN at procurement — not today's Chhatni Assign.
		procurement_chhatni = _procurement_chhatni_rate(grn)
		chhatni_rate = procurement_chhatni
		if chhatni_rate <= 0:
			chhatni_from_assign = flt(chhatni_row.get("chutney_quantity_kg_per_quintal")) or flt(
				chhatni_row.get("chutney_percentage")
			)
			chhatni_rate = _current_chhatni_rate(chhatni_from_assign, season_master, ppc_link, mill_link)
		chhatni_assigned_kg = chhatni_rate
		chhatni_assigned_pct = chhatni_rate

		tp_filled = _("Yes") if tp_qty > 0 and total_received >= tp_qty else _("No")
		received_minus_tp = flt(max(total_received - tp_qty, 0), 3)
		total_deduction = flt(grn.get("total_deduction"))
		received_pct = received_chhatni_pct(total_deduction, tp_qty)

		if tp_qty > 0 and total_received < tp_qty:
			chhatni_status = _("Chhatni Not Received")
		elif tp_qty > 0 and total_received >= tp_qty:
			chhatni_status = (
				chhatni_fulfillment_status(
					tp_qty,
					total_received,
					chhatni_rate,
					total_deduction,
				)
				or _("Chhatni Pending")
			)
		else:
			chhatni_status = ""

		data.append(
			{
				"season": (tp.season or "").strip(),
				"ppc_display": _ppc_display(ppc_link, tp.ppc),
				"mill_display": _mill_display(mill_link, tp.miller),
				"transit_pass_no": tp.transit_pass_no,
				"pass_unique_key": pass_key,
				"chhatni_assigned_kg": chhatni_assigned_kg,
				"chhatni_assigned_pct": chhatni_assigned_pct,
				"tp_quantity": tp_qty,
				"total_received": total_received,
				"tp_filled": tp_filled,
				"received_chhatni_pct": received_pct,
				"chhatni_status": chhatni_status,
				"received_minus_tp": received_minus_tp,
				"chhatni_assign": chhatni_row.get("name"),
			}
		)

	return data


def _procurement_chhatni_rate(grn_summary: dict) -> float:
	"""Chhatni % stamped on GRN when this TP was received (TP-completing GRN first)."""
	if not grn_summary:
		return 0.0
	rate = flt(grn_summary.get("procurement_chhatni"))
	if rate > 0:
		return rate
	return flt(grn_summary.get("grn_chhatni_max"))


def _current_chhatni_rate(chhatni_assigned_kg, season_master, ppc_link, mill_link):
	"""Fallback when no government GRN yet — current assign / target allocation."""
	rate = flt(chhatni_assigned_kg)
	if rate > 0:
		return rate

	if season_master and ppc_link and mill_link:
		ta_chhatni = frappe.db.get_value(
			"Target Allocation",
			{"season": season_master, "ppc_name": ppc_link, "mill_name": mill_link},
			"chhatni",
		)
		if flt(ta_chhatni) > 0:
			return flt(ta_chhatni)

	return 0


def _build_grn_summary_by_pass() -> dict[str, dict]:
	rows = frappe.db.sql(
		"""
		SELECT
			pass_unique_key,
			MAX(tp_cumulative_received) AS total_received,
			SUM(received_quantity) AS sum_received,
			SUM(deduction) AS total_deduction,
			MAX(tp_quantity) AS tp_qty_grn,
			MAX(CASE WHEN tp_fulfillment_status = 'TP Completed' THEN chhatni END) AS procurement_chhatni,
			MAX(CASE WHEN tp_fulfillment_status = 'TP Completed' THEN chhatni_fulfillment_status END)
				AS chhatni_status_completed,
			MAX(chhatni) AS grn_chhatni_max
		FROM `tabGRN Note`
		WHERE is_local_procurement = 0
			AND docstatus < 2
			AND IFNULL(pass_unique_key, '') != ''
		GROUP BY pass_unique_key
		""",
		as_dict=True,
	)
	return {row.pass_unique_key: row for row in rows if row.pass_unique_key}


def _ppc_display(ppc_link: str | None, fallback: str | None) -> str:
	if ppc_link and frappe.db.exists("PPC Master", ppc_link):
		name = frappe.db.get_value("PPC Master", ppc_link, "ppc_name")
		if name:
			return name.strip()
		return ppc_link
	return (fallback or "").strip()


def _mill_display(mill_link: str | None, fallback: str | None) -> str:
	if mill_link and frappe.db.exists("Mill Master", mill_link):
		code = frappe.db.get_value("Mill Master", mill_link, "miller_code")
		return (code or mill_link).strip()
	return (fallback or "").strip()
