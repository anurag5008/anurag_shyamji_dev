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
	evaluate_chhatni_fulfillment,
	required_chhatni_qt,
	tp_chhatni_balance_qt,
)
from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Season"), "fieldname": "season", "fieldtype": "Data", "width": 120},
		{"label": _("PPC Name"), "fieldname": "ppc_name", "fieldtype": "Data", "width": 200},
		{
			"label": _("Mill Name (Code)"),
			"fieldname": "mill_name",
			"fieldtype": "Data",
			"width": 220,
		},
		{"label": _("TP No"), "fieldname": "transit_pass_no", "fieldtype": "Data", "width": 90},
		{
			"label": _("Pass Unique Key"),
			"fieldname": "pass_unique_key",
			"fieldtype": "Link",
			"options": "PPAS Transit Pass",
			"width": 200,
			"hidden": 1,
		},
		{
			"label": _("TP Quantity (QT)"),
			"fieldname": "tp_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{
			"label": _("Total Quantity Received (QT)"),
			"fieldname": "total_received",
			"fieldtype": "Float",
			"precision": 3,
			"width": 170,
		},
		{
			"label": _("Chhatni Assigned"),
			"fieldname": "chhatni_assigned",
			"fieldtype": "Float",
			"precision": 2,
			"width": 120,
		},
		{"label": _("TP Status"), "fieldname": "tp_status", "fieldtype": "Data", "width": 120},
		{
			"label": _("Chhatni Status"),
			"fieldname": "chhatni_status",
			"fieldtype": "Data",
			"width": 190,
		},
		{
			"label": _("Received − TP + Chhatni (QT)"),
			"fieldname": "received_minus_tp_chhatni",
			"fieldtype": "Float",
			"precision": 3,
			"width": 190,
		},
		{
			"label": _("Extra after TP (QT)"),
			"fieldname": "extra_after_tp",
			"fieldtype": "Float",
			"precision": 3,
			"width": 140,
		},
		{
			"label": _("Chhatni Received Qty (QT)"),
			"fieldname": "chhatni_received_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 170,
		},
		{"label": _("Jute Pkt"), "fieldname": "jute_pkt", "fieldtype": "Int", "width": 90},
		{"label": _("Plastic Pkt"), "fieldname": "plastic_pkt", "fieldtype": "Int", "width": 100},
		{"label": _("No. of Bags"), "fieldname": "no_of_bags", "fieldtype": "Int", "width": 100},
		{"label": _("Total Bags"), "fieldname": "total_bags", "fieldtype": "Int", "width": 100},
		{
			"label": _("Gunny (Gross / Cut)"),
			"fieldname": "gunny_type",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"label": _("Gunny Weight (QT)"),
			"fieldname": "gunny_weight",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("Deduction (QT)"),
			"fieldname": "deduction",
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{"label": _("RST"), "fieldname": "rst_count", "fieldtype": "Data", "width": 110},
		{"label": _("Entry"), "fieldname": "entry_count", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	grns = frappe.get_all(
		"GRN Note",
		filters={"is_local_procurement": 0, "docstatus": ["<", 2]},
		fields=[
			"name",
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
		total_received = flt(sum(flt(doc.received_quantity) for doc in docs), 3)
		if not total_received:
			total_received = flt(max((flt(doc.tp_cumulative_received) for doc in docs), default=0), 3)
		if not total_received:
			total_received = flt(sum(flt(doc.net_weight) for doc in docs), 3)

		chhatni_assigned = _assigned_chhatni(docs)
		tp_complete = _tp_is_complete(docs, tp_qty, total_received)
		if tp_complete:
			chhatni_status = _chhatni_status(docs, tp_qty, total_received, chhatni_assigned)
			balance = tp_chhatni_balance_qt(tp_qty, total_received, chhatni_assigned)
			extra = flt(max(total_received - tp_qty, 0), 3)
			tp_status = _("TP Completed")
		else:
			# Chhatni is not calculated until the transit pass quantity is fully received.
			chhatni_status = "0"
			balance = 0
			extra = 0
			tp_status = _("In Progress")

		rst_lines = _rst_lines(docs, wbm_by_name, bags_by_wbm)
		entry_lines = entries_by_pass.get(key, [])
		sample = docs[-1]
		mill_label, mill_code = _mill_label(key, sample.mill_name, mill_companies)
		if mill_filter and mill_filter not in (mill_code, (sample.mill_name or "").strip()):
			continue
		if tp_complete and chhatni_status in ("Chhatni Received", "Over Filled Chhatni Received"):
			chhatni_received_qty = required_chhatni_qt(tp_qty, chhatni_assigned)
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
				"chhatni_assigned": chhatni_assigned,
				"tp_status": tp_status,
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
				"rst_count": len(rst_lines),
				"entry_count": len(entry_lines),
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
			(wbm.get("actual_truck_no") or "").strip()
			or (wbm.get("vehicle_no") or "").strip()
			or (doc.vehicle_no or "").strip()
		)
		rst_no = (doc.rst_no or wbm.get("rst_no") or "").strip()
		if not (rst_no or wbm_name):
			continue
		jute = cint(bags.get("jute"))
		plastic = cint(bags.get("plastic"))
		gunny_weight = flt(bags.get("gunny_weight") or 0, 3)
		if not gunny_weight:
			gunny_weight = flt(wbm.get("gunny_weight"), 3)
		total_bags = cint(wbm.get("total_bags")) or (jute + plastic)
		lines.append(
			{
				"rst_no": rst_no,
				"deduction": flt(wbm.get("deduction") if wbm else doc.deduction, 3),
				"weigh_bridge_measurement": wbm_name,
				"actual_vehicle_no": vehicle,
				"jute_pkt": jute,
				"plastic_pkt": plastic,
				"no_of_bags": cint(wbm.get("no_of_bags")),
				"total_bags": total_bags,
				"gunny_type": (wbm.get("gunny_type") or doc.gunny_type or "").strip(),
				"gunny_weight": gunny_weight,
			}
		)
	return lines


def _assigned_chhatni(docs) -> float:
	for doc in docs:
		if (doc.tp_fulfillment_status or "").strip() == "TP Completed" and flt(doc.chhatni) > 0:
			return flt(doc.chhatni, 2)
	return flt(max((flt(doc.chhatni) for doc in docs), default=0), 2)


def _tp_is_complete(docs, tp_qty: float, total_received: float) -> bool:
	if any((doc.tp_fulfillment_status or "").strip() == "TP Completed" for doc in docs):
		return True
	return tp_qty > 0 and total_received >= tp_qty


def _chhatni_status(docs, tp_qty: float, total_received: float, chhatni_assigned: float) -> str:
	for doc in reversed(docs):
		if (doc.tp_fulfillment_status or "").strip() != "TP Completed":
			continue
		stored = (doc.chhatni_fulfillment_status or "").strip()
		if stored:
			return stored
	status, _remark = evaluate_chhatni_fulfillment(tp_qty, total_received, chhatni_assigned)
	return status or "0"


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
