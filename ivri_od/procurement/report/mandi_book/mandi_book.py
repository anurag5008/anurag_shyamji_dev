# Copyright (c) 2026, Profezzo and contributors
"""Mandi Book: one row per transit pass, summarised from GRN Note."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt

from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.ppc_pass_metrics import ppc_display_name
from ivri_od.procurement.grn_tp_fulfillment import (
	CHHATNI_NOT_RECEIVED,
	CHHATNI_RECEIVED,
	EXTRA_CHHATNI_RECEIVED,
	evaluate_chhatni_fulfillment,
	excess_tp_received_quantity,
	grn_received_quantity,
	pending_tp_quantity,
	received_chhatni_pct,
	remaining_tp_quantity,
	required_chhatni_qt,
	tp_chhatni_balance_qt,
	tp_fulfillment_status,
)
from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Season"), "fieldname": "season", "fieldtype": "Data", "width": 110},
		{"label": _("PPC Name"), "fieldname": "ppc_name", "fieldtype": "Data", "width": 180},
		{
			"label": _("Mill Name"),
			"fieldname": "mill_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{"label": _("TP No."), "fieldname": "transit_pass_no", "fieldtype": "Data", "width": 90},
		{
			"label": _("Pass Unique Key"),
			"fieldname": "pass_unique_key",
			"fieldtype": "Link",
			"options": "PPAS Transit Pass",
			"width": 200,
			"hidden": 1,
		},
		{
			"label": _("TP Qty"),
			"fieldname": "tp_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"label": _("Total Qty Received"),
			"fieldname": "total_received",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Pending Qty (QTL)"),
			"fieldname": "pending_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 140,
		},
		{
			"label": _("Excess Received Qty (QTL)"),
			"fieldname": "excess_received_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 170,
		},
		{"label": _("TP Status"), "fieldname": "tp_status", "fieldtype": "Data", "width": 110},
		{"label": _("Jute Bags"), "fieldname": "jute_pkt", "fieldtype": "Int", "width": 95},
		{"label": _("Plastic Bags"), "fieldname": "plastic_pkt", "fieldtype": "Int", "width": 95},
		{"label": _("Total Bags"), "fieldname": "total_bags", "fieldtype": "Int", "width": 95},
		{
			"label": _("Assigned Chhatni %"),
			"fieldname": "chhatni_assigned",
			"fieldtype": "Float",
			"precision": 2,
			"width": 135,
		},
		{
			"label": _("Received Chhatni %"),
			"fieldname": "actual_chhatni_pct",
			"fieldtype": "Percent",
			"precision": 2,
			"width": 135,
		},
		{
			"label": _("Chhatni Status"),
			"fieldname": "chhatni_status",
			"fieldtype": "Data",
			"width": 180,
		},
		{"label": _("GRN Details"), "fieldname": "grn_count", "fieldtype": "Data", "width": 125},
		{"label": _("Entry Details"), "fieldname": "entry_count", "fieldtype": "Data", "width": 125},
	]


def get_data(filters):
	grns = frappe.get_all(
		"GRN Note",
		filters={"is_local_procurement": 0, "docstatus": ["<", 2]},
		fields=[
			"name",
			"grn_no",
			"pass_unique_key",
			"ppc",
			"ppc_name",
			"mill_name",
			"cmr_season",
			"transit_pass_no",
			"tp_quantity",
			"chhatni",
			"received_quantity",
			"net_weight",
			"gross_vehicle_weight",
			"tare_weight",
			"gross_weight",
			"gunny_weight",
			"tp_cumulative_received",
			"tp_fulfillment_status",
			"chhatni_fulfillment_status",
			"rst_no",
			"gunny_type",
			"deduction",
			"weigh_bridge_measurement",
			"vehicle_no",
			"receipt_datetime",
			"creation",
		],
		order_by="receipt_datetime asc, creation asc",
	)
	if not grns:
		return []

	grouped: dict[str, list] = defaultdict(list)
	for grn in grns:
		key = (grn.pass_unique_key or "").strip()
		if key:
			grouped[key].append(grn)

	wbm_by_name = _weigh_bridges_for(grns)
	bags_by_wbm = _bags_by_wbm(list(wbm_by_name))
	entries_by_pass = _entries_for(list(grouped))
	ppc_filter = _ppc_filter_values(filters.get("ppc_name"))
	season_filter = (filters.get("season") or "").strip()
	mill_filter = (filters.get("mill_name") or "").strip()
	tp_no_filter = (filters.get("transit_pass_no") or "").strip()
	mill_companies = _mill_companies(grouped)

	rows = []
	for key in sorted(
		grouped,
		key=lambda item: (_season_name(grouped[item]), _ppc_sort(grouped[item]), _tp_no(grouped[item]), item),
	):
		docs = grouped[key]
		season_name = _season_name(docs)
		if season_filter and season_filter not in _season_match_values(docs):
			continue
		if ppc_filter and not any(_ppc_matches(doc, ppc_filter) for doc in docs):
			continue
		tp_no = _tp_no(docs)
		if tp_no_filter and tp_no_filter.lower() not in (tp_no or "").lower():
			continue

		tp_qty = max((flt(doc.tp_quantity) for doc in docs), default=0)
		total_received = flt(sum(grn_received_quantity(doc) for doc in docs), 3)

		chhatni_assigned = _assigned_chhatni(docs)
		total_deduction = flt(sum(flt(doc.deduction) for doc in docs), 3)
		tp_status = tp_fulfillment_status(tp_qty, total_received)
		tp_complete = tp_status == "TP Completed"
		pending_qty = pending_tp_quantity(tp_qty, total_received)
		excess_qty = excess_tp_received_quantity(tp_qty, total_received)
		required_chhatni = required_chhatni_qt(tp_qty, chhatni_assigned)
		actual_chhatni_pct = received_chhatni_pct(total_deduction, tp_qty) if tp_qty > 0 else 0.0
		chhatni_status = _chhatni_status(docs, tp_qty, total_received, chhatni_assigned, total_deduction)
		balance = tp_chhatni_balance_qt(tp_qty, total_received, total_deduction)
		extra = excess_qty

		rst_lines = _rst_lines(docs, wbm_by_name, bags_by_wbm)
		entry_lines = entries_by_pass.get(key, [])
		sample = docs[-1]
		mill_label, mill_code = _mill_label(key, sample.mill_name, mill_companies)
		if mill_filter and mill_filter not in (mill_code, (sample.mill_name or "").strip()):
			continue
		if chhatni_status in (CHHATNI_RECEIVED, EXTRA_CHHATNI_RECEIVED, "Over Filled Chhatni Received"):
			chhatni_received_qty = required_chhatni
		else:
			chhatni_received_qty = 0
		gunny_types = []
		for line in rst_lines:
			if line["gunny_type"] and line["gunny_type"] not in gunny_types:
				gunny_types.append(line["gunny_type"])
		rows.append(
			{
				"season": season_name,
				"ppc_name": ppc_display_name(sample.ppc or sample.ppc_name),
				"mill_name": mill_label,
				"transit_pass_no": tp_no,
				"pass_unique_key": key,
				"tp_quantity": tp_qty,
				"total_received": total_received,
				"pending_qty": pending_qty,
				"pending_quantity": pending_qty,
				"remaining_quantity": pending_qty,
				"excess_received_qty": excess_qty,
				"excess_received_quantity": excess_qty,
				"tp_status": tp_status,
				"chhatni_assigned": chhatni_assigned,
				"required_chhatni": required_chhatni,
				"actual_chhatni_pct": actual_chhatni_pct,
				"chhatni_status": chhatni_status,
				"received_minus_tp_chhatni": balance,
				"extra_after_tp": extra,
				"chhatni_received_qty": chhatni_received_qty,
				"jute_pkt": sum(line["jute_pkt"] for line in rst_lines),
				"plastic_pkt": sum(line["plastic_pkt"] for line in rst_lines),
				"no_of_bags": sum(line["no_of_bags"] for line in rst_lines),
				"total_bags": sum(line["total_bags"] for line in rst_lines),
				"gunny_type": " / ".join(gunny_types),
				"gunny_weight": flt(sum(line["gunny_weight"] for line in rst_lines), 3),
				"deduction": flt(sum(line["deduction"] for line in rst_lines), 3),
				"grn_count": len(rst_lines),
				"rst_count": len(rst_lines),
				"entry_count": len(entry_lines),
				"grn_lines": rst_lines,
				"rst_lines": rst_lines,
				"entry_lines": entry_lines,
			}
		)
	return rows


def _season_name(docs) -> str:
	for doc in docs:
		season = (doc.cmr_season or "").strip()
		if season:
			return season
	return ""


def _season_match_values(docs) -> set[str]:
	values = set()
	for doc in docs:
		season = (doc.cmr_season or "").strip()
		if not season:
			continue
		values.add(season)
		resolved = resolve_season_master_name(season)
		if resolved:
			values.add(resolved)
	return values


def _mill_companies(grouped: dict) -> dict[str, str]:
	codes = {(key.partition("-")[0].strip()) for key in grouped if key.partition("-")[0].strip()}
	if not codes:
		return {}
	rows = frappe.get_all(
		"Mill Master",
		filters={"name": ["in", list(codes)]},
		fields=["name", "company"],
	)
	return {row.name: (row.company or "").strip() for row in rows}


def _mill_label(pass_key: str, miller_text: str | None, companies: dict[str, str]) -> tuple[str, str]:
	code = (pass_key or "").partition("-")[0].strip()
	if code not in companies:
		resolved = resolve_mill_master_name(pass_key, miller_text) or ""
		if resolved:
			code = resolved
			if code not in companies:
				company = frappe.db.get_value("Mill Master", code, "company") or ""
				companies[code] = (company or "").strip()
	company = companies.get(code) or ""
	text = (miller_text or "").strip()
	if company and code:
		return f"{company} ({code})", code
	if text and code and code not in text:
		return f"{text} ({code})", code
	return text or code, code


def _weigh_bridges_for(grns) -> dict[str, dict]:
	names = sorted(
		{(grn.weigh_bridge_measurement or "").strip() for grn in grns if (grn.weigh_bridge_measurement or "").strip()}
	)
	if not names:
		return {}
	rows = frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"name": ["in", names]},
		fields=[
			"name",
			"actual_truck_no",
			"vehicle_no",
			"truck_no_in_tp",
			"load_weight",
			"tare_weight",
			"gross_weight",
			"net_weight",
			"deduction",
			"rst_no",
			"gunny_type",
			"gunny_weight",
			"no_of_bags",
			"total_bags",
		],
	)
	return {row.name: row for row in rows}


def _bags_by_wbm(wbm_names: list[str]) -> dict[str, dict]:
	if not wbm_names:
		return {}
	rows = frappe.get_all(
		"Weigh Bridge Bag Detail",
		filters={"parent": ["in", wbm_names], "parenttype": "Weigh Bridge Measurement"},
		fields=["parent", "jute_bags", "plastic_bags", "gunny_weight_qt"],
	)
	grouped: dict[str, dict] = defaultdict(lambda: {"jute": 0, "plastic": 0, "gunny_weight": 0.0})
	for row in rows:
		bucket = grouped[row.parent]
		bucket["jute"] += cint(row.jute_bags)
		bucket["plastic"] += cint(row.plastic_bags)
		bucket["gunny_weight"] += flt(row.gunny_weight_qt)
	return grouped


def _entries_for(pass_keys: list[str]) -> dict[str, list[dict]]:
	if not pass_keys:
		return {}
	rows = frappe.get_all(
		"Entry",
		filters={"pass_unique_key": ["in", pass_keys], "docstatus": ["<", 2]},
		fields=[
			"name",
			"pass_unique_key",
			"agent_name",
			"entry_quantity",
			"entry_price_per_quintal",
			"total_amount",
		],
		order_by="creation asc",
	)
	grouped: dict[str, list[dict]] = defaultdict(list)
	for row in rows:
		key = (row.pass_unique_key or "").strip()
		grouped[key].append(
			{
				"entry": row.name,
				"agent_name": (row.agent_name or "").strip(),
				"entry_quantity": flt(row.entry_quantity, 3),
				"entry_price_per_quintal": flt(row.entry_price_per_quintal, 2),
				"total_amount": flt(row.total_amount, 2),
			}
		)
	return grouped


def _rst_lines(docs, wbm_by_name: dict, bags_by_wbm: dict) -> list[dict]:
	lines = []
	for doc in docs:
		wbm_name = (doc.weigh_bridge_measurement or "").strip()
		wbm = wbm_by_name.get(wbm_name) or {}
		bags = bags_by_wbm.get(wbm_name) or {}
		vehicle = (
			(doc.vehicle_no or "").strip()
			or (wbm.get("actual_truck_no") or "").strip()
			or (wbm.get("vehicle_no") or "").strip()
		)
		rst_no = (doc.rst_no or wbm.get("rst_no") or "").strip()
		if not (rst_no or wbm_name or doc.name):
			continue
		jute = cint(bags.get("jute"))
		plastic = cint(bags.get("plastic"))
		gunny_weight = flt(doc.gunny_weight) or flt(bags.get("gunny_weight") or 0, 3)
		if not gunny_weight:
			gunny_weight = flt(wbm.get("gunny_weight"), 3)
		total_bags = cint(wbm.get("total_bags")) or (jute + plastic)

		load_wt = flt(doc.gross_vehicle_weight) or flt(wbm.get("load_weight"), 3)
		tare_wt = flt(doc.tare_weight) or flt(wbm.get("tare_weight"), 3)
		gross_wt = flt(doc.gross_weight) or flt(wbm.get("gross_weight"), 3)
		if not gross_wt and load_wt and tare_wt:
			gross_wt = flt(load_wt - tare_wt, 3)
		if not load_wt and gross_wt and tare_wt:
			load_wt = flt(gross_wt + tare_wt, 3)

		deduction = flt(wbm.get("deduction") if (wbm and wbm.get("deduction") is not None) else doc.deduction, 3)
		net_wt = flt(doc.net_weight) or flt(wbm.get("net_weight"), 3)
		if not net_wt and gross_wt:
			net_wt = flt(gross_wt - gunny_weight - deduction, 3)

		lines.append(
			{
				"grn_no": (doc.grn_no or doc.name or "").strip(),
				"grn_name": (doc.name or "").strip(),
				"rst_no": rst_no,
				"vehicle_no": vehicle,
				"load_weight": load_wt,
				"tare_weight": tare_wt,
				"gross_weight": gross_wt,
				"gunny_type": (doc.gunny_type or wbm.get("gunny_type") or "").strip(),
				"gunny_weight": gunny_weight,
				"deduction": deduction,
				"net_weight": net_wt,
				"weigh_bridge_measurement": wbm_name,
				"actual_vehicle_no": vehicle,
				"jute_pkt": jute,
				"plastic_pkt": plastic,
				"no_of_bags": cint(wbm.get("no_of_bags")),
				"total_bags": total_bags,
			}
		)
	return lines


def _assigned_chhatni(docs) -> float:
	for doc in docs:
		if (doc.tp_fulfillment_status or "").strip() == "TP Completed" and flt(doc.chhatni) > 0:
			return flt(doc.chhatni, 2)
	return flt(max((flt(doc.chhatni) for doc in docs), default=0), 2)


def _tp_is_complete(docs, tp_qty: float, total_received: float) -> bool:
	return flt(tp_qty) > 0 and flt(total_received) >= flt(tp_qty)


def _chhatni_status(docs, tp_qty: float, total_received: float, chhatni_assigned: float, total_deduction: float) -> str:
	status, _remark = evaluate_chhatni_fulfillment(tp_qty, total_received, chhatni_assigned, total_deduction)
	return status or CHHATNI_NOT_RECEIVED


def _tp_no(docs) -> str:
	for doc in docs:
		number = (doc.transit_pass_no or "").strip()
		if number:
			return number
	return ""


def _ppc_sort(docs) -> str:
	sample = docs[-1]
	return ((sample.ppc_name or sample.ppc or "").strip()).lower()


def _ppc_filter_values(ppc_name: str | None) -> set[str]:
	link = (ppc_name or "").strip()
	if not link:
		return set()
	values = {link}
	master_label = frappe.db.get_value("PPC Master", link, "ppc_name")
	if master_label:
		values.add(master_label.strip())
	return {value for value in values if value}


def _ppc_matches(doc, values: set[str]) -> bool:
	ppc = (doc.ppc or "").strip()
	ppc_name = (doc.ppc_name or "").strip()
	for value in values:
		if value in (ppc, ppc_name) or value in ppc or value in ppc_name:
			return True
	return False
