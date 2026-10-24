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
	actual_chhatni_status,
	excess_tp_received_quantity,
	pending_tp_quantity,
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
		{"label": _("PPC Name"), "fieldname": "ppc_name", "fieldtype": "Data", "width": 260},
		{
			"label": _("Mill Name"),
			"fieldname": "mill_name",
			"fieldtype": "Data",
			"width": 480,
		},
		{"label": _("TP No."), "fieldname": "transit_pass_no", "fieldtype": "Data", "width": 95},
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
			"width": 105,
		},
		{
			"label": _("Total Gross Wt"),
			"fieldname": "total_gross_weight",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("Gunny Type"),
			"fieldname": "summary_gunny_type",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": _("Total Gunny Wt"),
			"fieldname": "total_gunny_weight",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("Total Deduction Received"),
			"fieldname": "total_deduction_received",
			"fieldtype": "Float",
			"precision": 3,
			"width": 180,
		},
		{
			"label": _("Chhatni (QT)"),
			"fieldname": "chhatni_received_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 125,
		},
		{
			"label": _("Total Qty Received"),
			"fieldname": "total_received",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Assigned Chhatni %"),
			"fieldname": "chhatni_assigned",
			"fieldtype": "Float",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Received Chhatni %"),
			"fieldname": "actual_chhatni_pct",
			"fieldtype": "Percent",
			"precision": 2,
			"width": 140,
		},
		{
			"label": _("Chhatni Status"),
			"fieldname": "chhatni_status",
			"fieldtype": "Data",
			"width": 185,
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
		{"label": _("TP Status"), "fieldname": "tp_status", "fieldtype": "Data", "width": 130},
		{"label": _("Jute Bags"), "fieldname": "jute_pkt", "fieldtype": "Int", "width": 95},
		{"label": _("Plastic Bags"), "fieldname": "plastic_pkt", "fieldtype": "Int", "width": 95},
		{"label": _("Total Bags"), "fieldname": "total_bags", "fieldtype": "Int", "width": 95},
		{"label": _("Entry"), "fieldname": "entry", "fieldtype": "Link", "options": "Entry", "width": 125},
		{"label": _("Agent Name"), "fieldname": "agent_name", "fieldtype": "Data", "width": 150},
		{"label": _("Entry Qty"), "fieldname": "entry_quantity", "fieldtype": "Float", "precision": 3, "width": 110},
		{"label": _("Price per Quintal"), "fieldname": "entry_price_per_quintal", "fieldtype": "Float", "precision": 2, "width": 135},
		{"label": _("Total Amount"), "fieldname": "total_amount", "fieldtype": "Float", "precision": 2, "width": 135},
		{"label": _("GRN No."), "fieldname": "grn_no", "fieldtype": "Link", "options": "GRN Note", "width": 135},
		{"label": _("RST No."), "fieldname": "rst_no", "fieldtype": "Data", "width": 120},
		{"label": _("Vehicle No."), "fieldname": "vehicle_no", "fieldtype": "Data", "width": 125},
		{"label": _("Load Wt"), "fieldname": "load_weight", "fieldtype": "Float", "precision": 3, "width": 105},
		{"label": _("Tare Wt"), "fieldname": "tare_weight", "fieldtype": "Float", "precision": 3, "width": 105},
		{"label": _("Gross Wt"), "fieldname": "gross_weight", "fieldtype": "Float", "precision": 3, "width": 105},
		{"label": _("Gunny Type"), "fieldname": "gunny_type", "fieldtype": "Data", "width": 120},
		{"label": _("Gunny Wt"), "fieldname": "gunny_weight", "fieldtype": "Float", "precision": 3, "width": 105},
		{"label": _("Deduction"), "fieldname": "deduction", "fieldtype": "Float", "precision": 3, "width": 105},
		{"label": _("Net Wt"), "fieldname": "net_weight", "fieldtype": "Float", "precision": 3, "width": 105},
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
	chhatni_by_pass = _chhatni_for(list(grouped))
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

		rst_lines = _rst_lines(docs, wbm_by_name, bags_by_wbm)
		total_gross_weight = flt(sum(line["gross_weight"] for line in rst_lines), 3)
		total_gunny_weight = flt(sum(line["gunny_weight"] for line in rst_lines), 3)
		total_deduction_received = flt(sum(line["deduction"] for line in rst_lines), 3)
		# Actual chhatni from saved Chhatni records of this pass (Pass Unique Key = TP + PPC + season).
		chhatni = chhatni_by_pass.get(key) or {"chhatni_qt": 0.0, "received_chhatni_pct": 0.0}
		actual_chhatni_qt = chhatni["chhatni_qt"]
		# Total Qty Received = Total Gross Wt - Total Gunny Wt - Total Deduction Received - Chhatni (QT).
		total_received = flt(
			max(total_gross_weight - total_gunny_weight - total_deduction_received - actual_chhatni_qt, 0.0), 3
		)

		chhatni_assigned = _assigned_chhatni(docs)
		total_deduction = flt(sum(flt(doc.deduction) for doc in docs), 3)
		tp_status = tp_fulfillment_status(tp_qty, total_received)
		tp_complete = tp_status == "TP Completed"
		pending_qty = pending_tp_quantity(tp_qty, total_received)
		required_chhatni = required_chhatni_qt(tp_qty, chhatni_assigned)
		# Total Qty Received is already after Chhatni, so excess is what is left above TP Qty.
		excess_qty = excess_tp_received_quantity(tp_qty, total_received)
		# Received Chhatni % as saved on the Chhatni record (Chhatni QT ÷ TP Quantity × 100).
		received_pct = chhatni["received_chhatni_pct"]
		chhatni_status = actual_chhatni_status(tp_qty, received_pct, chhatni_assigned)
		balance = tp_chhatni_balance_qt(tp_qty, total_received, total_deduction)
		extra = excess_qty

		entry_lines = entries_by_pass.get(key, [])
		sample = docs[-1]
		mill_label, mill_code = _mill_label(key, sample.mill_name, mill_companies)
		if mill_filter and mill_filter not in (mill_code, (sample.mill_name or "").strip()):
			continue
		chhatni_received_qty = actual_chhatni_qt
		gunny_types = []
		for line in rst_lines:
			if line["gunny_type"] and line["gunny_type"] not in gunny_types:
				gunny_types.append(line["gunny_type"])

		tp_summary = {
			"season": season_name,
			"ppc_name": ppc_display_name(sample.ppc or sample.ppc_name),
			"mill_name": mill_label,
			"transit_pass_no": tp_no,
			"pass_unique_key": key,
			"tp_key": key,
			"tp_quantity": tp_qty,
			"total_gross_weight": total_gross_weight,
			"total_gross_wt": total_gross_weight,
			"summary_gunny_type": " / ".join(gunny_types),
			"total_gunny_weight": total_gunny_weight,
			"total_gunny_wt": total_gunny_weight,
			"total_deduction_received": total_deduction_received,
			"total_deduction": total_deduction_received,
			"total_received": total_received,
			"pending_qty": pending_qty,
			"pending_quantity": pending_qty,
			"remaining_quantity": pending_qty,
			"excess_received_qty": excess_qty,
			"excess_received_quantity": excess_qty,
			"tp_status": tp_status,
			"jute_pkt": sum(line["jute_pkt"] for line in rst_lines),
			"plastic_pkt": sum(line["plastic_pkt"] for line in rst_lines),
			"no_of_bags": sum(line["no_of_bags"] for line in rst_lines),
			"total_bags": sum(line["total_bags"] for line in rst_lines),
			"chhatni_assigned": chhatni_assigned,
			"required_chhatni": required_chhatni,
			"actual_chhatni_pct": received_pct,
			"chhatni_status": chhatni_status,
			"received_minus_tp_chhatni": balance,
			"extra_after_tp": extra,
			"chhatni_received_qty": chhatni_received_qty,
			"gunny_type_summary": " / ".join(gunny_types),
			"deduction_total": total_deduction,
			"grn_count": len(rst_lines),
			"rst_count": len(rst_lines),
			"entry_count": len(entry_lines),
			"grn_lines": rst_lines,
			"rst_lines": rst_lines,
			"entry_lines": entry_lines,
		}

		tp_blank = {
			"season": "",
			"ppc_name": "",
			"mill_name": "",
			"transit_pass_no": "",
			"pass_unique_key": "",
			"tp_key": key,
			"tp_quantity": None,
			"total_gross_weight": None,
			"total_gross_wt": None,
			"summary_gunny_type": "",
			"total_gunny_weight": None,
			"total_gunny_wt": None,
			"total_deduction_received": None,
			"total_deduction": None,
			"total_received": None,
			"pending_qty": None,
			"pending_quantity": None,
			"remaining_quantity": None,
			"excess_received_qty": None,
			"excess_received_quantity": None,
			"tp_status": "",
			"jute_pkt": None,
			"plastic_pkt": None,
			"no_of_bags": None,
			"total_bags": None,
			"chhatni_assigned": None,
			"required_chhatni": None,
			"actual_chhatni_pct": None,
			"chhatni_status": "",
			"received_minus_tp_chhatni": None,
			"extra_after_tp": None,
			"chhatni_received_qty": None,
			"gunny_type_summary": "",
			"deduction_total": None,
			"grn_count": None,
			"rst_count": None,
			"entry_count": None,
			"grn_lines": [],
			"rst_lines": [],
			"entry_lines": [],
		}

		# Detail rows: align Entry records sequentially alongside GRN records
		total_detail_rows = max(len(rst_lines), len(entry_lines))
		if total_detail_rows == 0:
			row = dict(tp_summary)
			row.update(_empty_grn_dict())
			row.update(_empty_entry_dict())
			row["detail_type"] = ""
			rows.append(row)
		else:
			for idx in range(total_detail_rows):
				base = tp_summary if idx == 0 else tp_blank
				row = dict(base)

				grn = rst_lines[idx] if idx < len(rst_lines) else None
				entry = entry_lines[idx] if idx < len(entry_lines) else None

				if grn:
					row.update(_grn_fields_dict(grn))
				else:
					row.update(_empty_grn_dict())

				if entry:
					row.update(_entry_fields_dict(entry))
				else:
					row.update(_empty_entry_dict())

				if grn and entry:
					row["detail_type"] = "GRN & Entry"
				elif grn:
					row["detail_type"] = "GRN"
				elif entry:
					row["detail_type"] = "Entry"
				else:
					row["detail_type"] = ""

				rows.append(row)

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
		qty = flt(row.entry_quantity, 3)
		rate = flt(row.entry_price_per_quintal, 2)
		amt = flt(row.total_amount, 2)
		if not amt and qty and rate:
			amt = flt(qty * rate, 2)
		grouped[key].append(
			{
				"entry": row.name,
				"agent_name": (row.agent_name or "").strip(),
				"entry_quantity": qty,
				"entry_price_per_quintal": rate,
				"total_amount": amt,
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


def _chhatni_for(pass_keys: list[str]) -> dict[str, dict]:
	"""Actual Chhatni QT and Received Chhatni % per pass from saved Chhatni records (one per pass).

	Records of one pass share its TP Quantity, so their Received % add up like their QT.
	"""
	if not pass_keys:
		return {}
	rows = frappe.get_all(
		"Chhatni",
		filters={"pass_unique_key": ["in", pass_keys]},
		fields=["name", "pass_unique_key", "chhatni_qt", "received_chhatni_pct"],
	)
	totals: dict[str, dict] = defaultdict(lambda: {"chhatni_qt": 0.0, "received_chhatni_pct": 0.0})
	seen: set[str] = set()
	for row in rows:
		if row.name in seen:
			continue
		seen.add(row.name)
		bucket = totals[(row.pass_unique_key or "").strip()]
		bucket["chhatni_qt"] = flt(bucket["chhatni_qt"] + flt(row.chhatni_qt), 3)
		bucket["received_chhatni_pct"] = flt(bucket["received_chhatni_pct"] + flt(row.received_chhatni_pct), 2)
	return totals


def _assigned_chhatni(docs) -> float:
	for doc in docs:
		if (doc.tp_fulfillment_status or "").strip() == "TP Completed" and flt(doc.chhatni) > 0:
			return flt(doc.chhatni, 2)
	return flt(max((flt(doc.chhatni) for doc in docs), default=0), 2)


def _tp_is_complete(docs, tp_qty: float, total_received: float) -> bool:
	return flt(tp_qty) > 0 and flt(total_received) >= flt(tp_qty)


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


def _grn_fields_dict(line: dict) -> dict:
	return {
		"grn_no": (line.get("grn_no") or line.get("grn_name") or "").strip(),
		"grn_name": (line.get("grn_name") or "").strip(),
		"rst_no": (line.get("rst_no") or "").strip(),
		"vehicle_no": (line.get("vehicle_no") or line.get("actual_vehicle_no") or "").strip(),
		"load_weight": flt(line.get("load_weight"), 3),
		"tare_weight": flt(line.get("tare_weight"), 3),
		"gross_weight": flt(line.get("gross_weight"), 3),
		"gunny_type": (line.get("gunny_type") or "").strip(),
		"gunny_weight": flt(line.get("gunny_weight"), 3),
		"deduction": flt(line.get("deduction"), 3),
		"net_weight": flt(line.get("net_weight"), 3),
		"weigh_bridge_measurement": (line.get("weigh_bridge_measurement") or "").strip(),
	}


def _empty_grn_dict() -> dict:
	return {
		"grn_no": "",
		"grn_name": "",
		"rst_no": "",
		"vehicle_no": "",
		"load_weight": None,
		"tare_weight": None,
		"gross_weight": None,
		"gunny_type": "",
		"gunny_weight": None,
		"deduction": None,
		"net_weight": None,
		"weigh_bridge_measurement": "",
	}


def _entry_fields_dict(entry: dict) -> dict:
	return {
		"entry": (entry.get("entry") or "").strip(),
		"agent_name": (entry.get("agent_name") or "").strip(),
		"entry_quantity": flt(entry.get("entry_quantity"), 3),
		"entry_price_per_quintal": flt(entry.get("entry_price_per_quintal"), 2),
		"total_amount": flt(entry.get("total_amount"), 2),
	}


def _empty_entry_dict() -> dict:
	return {
		"entry": "",
		"agent_name": "",
		"entry_quantity": None,
		"entry_price_per_quintal": None,
		"total_amount": None,
	}

