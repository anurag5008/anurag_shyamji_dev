# Copyright (c) 2026, Profezzo and contributors
"""Entry Report: follows the Excel ENTRY sheet structure for procurement entries."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import miller_code_part
from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.ppc_pass_metrics import (
	get_ppc_season_target_map,
	make_ppc_resolver,
	mill_display_name,
	ppc_display_name,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Season"),
			"fieldname": "season",
			"fieldtype": "Link",
			"options": "Season Master",
			"width": 140,
		},
		{
			"label": _("PPC"),
			"fieldname": "ppc",
			"fieldtype": "Link",
			"options": "PPC Master",
			"width": 300,
		},
		{
			"label": _("TP No."),
			"fieldname": "tp_no",
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"label": _("TP Qty (QTL)"),
			"fieldname": "tp_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Mill Name"),
			"fieldname": "mill_name",
			"fieldtype": "Data",
			"width": 380,
		},
		{
			"label": _("Agent Name"),
			"fieldname": "agent_name",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Entry Qty (QTL)"),
			"fieldname": "entry_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 160,
		},
		{
			"label": _("Entry Price"),
			"fieldname": "entry_price",
			"fieldtype": "Float",
			"precision": 2,
			"width": 150,
		},
		{
			"label": _("Total Amount"),
			"fieldname": "total_amount",
			"fieldtype": "Float",
			"precision": 2,
			"width": 180,
		},
	]


def get_data(filters=None):
	filters = frappe._dict(filters or {})
	season_filter = (filters.get("season") or "").strip()
	ppc_filter = (filters.get("ppc_name") or filters.get("ppc") or "").strip()
	mill_filter = (filters.get("mill_name") or filters.get("mill") or "").strip()

	# 1. Fetch PPC Master rows for resolution
	ppc_master_rows = frappe.get_all(
		"PPC Master",
		fields=["name", "code", "ppc_name", "title"],
		order_by="ppc_name asc, name asc",
	)
	resolve_to_ppc_master = make_ppc_resolver(ppc_master_rows)

	# 2. Fetch authoritative Target Allocations
	target_map, ppc_season_totals = get_ppc_season_target_map(
		season=season_filter if season_filter else None,
		mill_name=mill_filter if mill_filter else None,
		ppc_master_rows=ppc_master_rows,
	)

	# 3. Fetch Mill Master for display names and codes
	all_mills = frappe.get_all(
		"Mill Master",
		fields=["name", "miller_code", "company"],
	)
	mill_name_by_code = {}
	for m in all_mills:
		company = (m.company or m.name or "").strip()
		if m.name:
			mill_name_by_code[m.name.casefold()] = company
		if m.miller_code:
			mill_name_by_code[m.miller_code.casefold()] = company

	# 4. Filter criteria for Entry DocType
	entry_conditions = {}
	if season_filter:
		canonical_season = resolve_season_master_name(season_filter) or season_filter
		entry_conditions["season"] = canonical_season

	entries = frappe.get_all(
		"Entry",
		filters=entry_conditions,
		fields=[
			"name",
			"season",
			"ppc_name",
			"tp_no",
			"pass_unique_key",
			"transit_pass_no",
			"tp_quantity",
			"agent_name",
			"entry_quantity",
			"entry_price_per_quintal",
			"total_amount",
			"creation",
		],
		order_by="creation desc",
	)

	if not entries:
		return []

	# 5. Pre-fetch linked PPAS Transit Passes in bulk
	pass_keys = {
		(e.pass_unique_key or "").strip() for e in entries if (e.pass_unique_key or "").strip()
	}
	tps_by_key = {}
	if pass_keys:
		tp_records = frappe.get_all(
			"PPAS Transit Pass",
			filters={"pass_unique_key": ["in", list(pass_keys)]},
			fields=[
				"name",
				"pass_unique_key",
				"transit_pass_no",
				"quantity",
				"miller",
				"season",
				"ppc",
			],
		)
		for tp in tp_records:
			key = (tp.pass_unique_key or tp.name or "").strip()
			if key:
				tps_by_key[key] = tp

	# Filter PPC if requested
	filter_ppc_doc = resolve_to_ppc_master(ppc_filter) if ppc_filter else None

	data = []
	for entry in entries:
		s = resolve_season_master_name(entry.season) or (entry.season or "").strip()
		pass_key = (entry.pass_unique_key or "").strip()
		tp = tps_by_key.get(pass_key)

		# Resolve Miller / Mill Name
		miller_raw = tp.miller if tp and tp.miller else pass_key
		mill_code = miller_code_part(miller_raw)
		mill_display = mill_name_by_code.get(mill_code.casefold()) or (
			mill_display_name(mill_code) if mill_code != "UNKNOWN" else ""
		)

		if mill_filter:
			if (
				mill_code.casefold() != mill_filter.casefold()
				and mill_display.casefold() != mill_filter.casefold()
			):
				continue

		# Resolve PPC authoritative from Target Allocation
		# Determine candidate PPC doc from entry/tp
		raw_ppc = entry.ppc_name or (tp.ppc if tp else None)
		p_doc = resolve_to_ppc_master(raw_ppc)

		if not p_doc:
			# If PPC cannot be resolved to a valid PPC Master record, exclude
			continue

		if filter_ppc_doc and p_doc.name != filter_ppc_doc.name:
			continue

		# Check if valid Target Allocation exists for this PPC in this season
		has_target = (
			target_map.get((s, p_doc.name, mill_code), 0.0) > 0
			or ppc_season_totals.get((s, p_doc.name), 0.0) > 0
		)
		if not has_target:
			# Exclude rows without valid Target Allocation
			continue

		ppc_label = (
			f"{p_doc.ppc_name}({p_doc.code})"
			if p_doc.code and p_doc.ppc_name and f"({p_doc.code})" not in p_doc.ppc_name
			else (p_doc.title or p_doc.ppc_name or p_doc.code or p_doc.name)
		)

		# TP No and TP Qty from PPAS Transit Pass (fallback to Entry fields)
		tp_number = (tp.transit_pass_no if tp and tp.transit_pass_no else None) or entry.tp_no or ""
		tp_quantity = flt(tp.quantity) if tp and flt(tp.quantity) > 0 else flt(entry.tp_quantity)

		entry_qty = flt(entry.entry_quantity, 3)
		entry_price = flt(entry.entry_price_per_quintal, 2)
		total_amount = flt(entry.total_amount, 2)
		if not total_amount and entry_qty and entry_price:
			total_amount = flt(entry_qty * entry_price, 2)

		data.append({
			"season": s,
			"ppc": ppc_label,
			"ppc_name": p_doc.name,
			"ppc_code": p_doc.code or p_doc.name,
			"tp_no": tp_number,
			"tp_qty": flt(tp_quantity, 3),
			"mill_name": mill_display,
			"agent_name": (entry.agent_name or "").strip(),
			"entry_qty": entry_qty,
			"entry_price": entry_price,
			"total_amount": total_amount,
		})

	return data
