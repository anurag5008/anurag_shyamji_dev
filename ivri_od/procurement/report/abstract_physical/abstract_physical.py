# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate

from ivri_od.procurement.doctype.season_master.season_master import (
	get_season_for_date,
	resolve_season_master_name,
)
from ivri_od.procurement.ppc_pass_metrics import (
	get_ppc_season_target_map,
	make_ppc_resolver,
	ppc_display_name,
)
from ivri_od.procurement.transit_pass_resolve import resolve_ppc_master_name


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(show_season=not filters.get("season")), get_data(filters)


def get_columns(show_season: bool = False):
	"""The Season column shows only while no season is chosen, to tell the seasons apart."""
	columns = [
		{
			"label": _("Season"),
			"fieldname": "season",
			"fieldtype": "Link",
			"options": "Season Master",
			"width": 120,
		},
	]
	return (columns if show_season else []) + [
		{
			"label": _("PPC"),
			"fieldname": "ppc",
			"fieldtype": "Link",
			"options": "PPC Master",
			"width": 240,
		},
		{
			"label": _("TP Quantity (QTL)"),
			"fieldname": "tp_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 140,
		},
		{
			"label": _("Physical Paddy (QTL)"),
			"fieldname": "physical_paddy",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Entry Qty (QTL)"),
			"fieldname": "entry_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("Chhatni Quantity (QTL)"),
			"fieldname": "chhatni_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 160,
		},
		{
			"label": _("Chhatni %"),
			"fieldname": "chhatni_pct",
			"fieldtype": "Percent",
			"precision": 2,
			"width": 110,
		},
	]


def get_data(filters):
	filters = frappe._dict(filters or {})
	season_filter = (filters.get("season") or "").strip()
	ppc_filter = (filters.get("ppc_name") or filters.get("ppc") or "").strip()

	# 1. Authoritative PPC master list from PPC Master DocType
	ppc_master_rows = frappe.get_all(
		"PPC Master",
		fields=["name", "code", "ppc_name", "title", "district"],
		order_by="ppc_name asc, name asc",
	)
	resolve_to_ppc_master = make_ppc_resolver(ppc_master_rows)

	if ppc_filter:
		filter_doc = resolve_to_ppc_master(ppc_filter)
		candidate_ppcs = [filter_doc] if filter_doc else []
	else:
		candidate_ppcs = ppc_master_rows

	# District filter: only the PPCs of this district (PPC Master).
	district_filter = (filters.get("district") or "").strip()
	if district_filter:
		candidate_ppcs = [
			p for p in candidate_ppcs if (p.get("district") or "").strip() == district_filter
		]

	# Season handling
	if season_filter:
		canonical_season = resolve_season_master_name(season_filter) or season_filter
		relevant_seasons = [canonical_season]
	else:
		relevant_seasons = frappe.get_all(
			"Season Master", pluck="name", order_by="year desc, crop_season asc"
		)
		if not relevant_seasons:
			discovered = set()
			for s in frappe.get_all("Target Allocation", pluck="season", distinct=True):
				if s:
					discovered.add(resolve_season_master_name(s) or s.strip())
			for s in frappe.get_all("Season Mapping", pluck="season", distinct=True):
				if s:
					discovered.add(resolve_season_master_name(s) or s.strip())
			for tp in frappe.get_all("PPAS Transit Pass", pluck="season", distinct=True):
				if tp:
					discovered.add(resolve_season_master_name(tp) or tp.strip())
			for grn in frappe.get_all("GRN Note", pluck="cmr_season", distinct=True):
				if grn:
					discovered.add(resolve_season_master_name(grn) or grn.strip())
			relevant_seasons = sorted(list(discovered))

	# Mill filter: Transit Passes, weighments, entries and Chhatni of this mill only. The mill is the
	# first part of the Pass Unique Key (a weighment without a pass takes the Mill No of its RST).
	mill_filter = (filters.get("mill_name") or "").strip()

	def mill_of_key(key: str) -> str:
		return (key or "").partition("-")[0].strip()

	# 2. Authoritative Target Allocation totals dynamically at runtime
	target_map, ppc_season_totals = get_ppc_season_target_map(
		season=season_filter if season_filter else None,
		mill_name=mill_filter or None,
		ppc_master_rows=ppc_master_rows,
	)

	# 2. Fetch PPAS Transit Passes in bulk
	all_tps = frappe.get_all(
		"PPAS Transit Pass",
		fields=["name", "season", "ppc", "quantity", "pass_unique_key"],
	)

	tp_meta_by_key = {}
	for tp in all_tps:
		key = (tp.pass_unique_key or tp.name or "").strip()
		if key:
			p_doc = resolve_to_ppc_master(tp.ppc)
			s_name = resolve_season_master_name(tp.season) or (tp.season or "").strip()
			tp_meta_by_key[key] = {
				"season": s_name,
				"ppc_doc": p_doc,
			}

	# 3. Fetch relevant GRNs in bulk
	grn_fields = [
		"name",
		"pass_unique_key",
		"cmr_season",
		"ppc",
		"ppc_name",
		"net_weight",
		"deduction",
	]
	if "entry_qty" in frappe.db.get_table_columns("GRN Note"):
		grn_fields.append("entry_qty")
	if "entry_quantity" in frappe.db.get_table_columns("GRN Note"):
		grn_fields.append("entry_quantity")

	all_grns = frappe.get_all(
		"GRN Note",
		filters={"is_local_procurement": 0, "docstatus": ["<", 2]},
		fields=grn_fields,
	)

	# 4. Pre-fetch GRN Entry Details in bulk
	grn_entry_map = defaultdict(float)
	if frappe.db.table_exists("GRN Entry Detail"):
		for row in frappe.get_all(
			"GRN Entry Detail",
			filters={"parenttype": "GRN Note", "parentfield": "entry_details"},
			fields=["parent", "entry_quantity"],
		):
			grn_entry_map[row.parent] += flt(row.entry_quantity)

	# 5. In-memory aggregation keyed by (season, ppc_master_name)
	aggregated = defaultdict(lambda: {
		"tp_quantity": 0.0,
		"physical_paddy": 0.0,
		"entry_qty": 0.0,
	})

	for tp in all_tps:
		if mill_filter and mill_of_key(tp.pass_unique_key or tp.name) != mill_filter:
			continue
		s = resolve_season_master_name(tp.season) or (tp.season or "").strip()
		p = resolve_to_ppc_master(tp.ppc)
		if not s or not p:
			# Skip transactions referencing PPCs not found in PPC Master
			continue
		aggregated[(s, p.name)]["tp_quantity"] += flt(tp.quantity)

	for grn in all_grns:
		pass_key = (grn.pass_unique_key or "").strip()
		if mill_filter and mill_of_key(pass_key) != mill_filter:
			continue
		tp_meta = tp_meta_by_key.get(pass_key, {})
		s = (
			resolve_season_master_name(grn.cmr_season)
			or (grn.cmr_season or "").strip()
			or tp_meta.get("season", "")
		)
		p = resolve_to_ppc_master(grn.ppc or grn.ppc_name) or tp_meta.get("ppc_doc")
		if not s or not p:
			# Skip transactions referencing PPCs not found in PPC Master
			continue
		entry_q = (
			flt(grn.get("entry_qty"))
			or flt(grn.get("entry_quantity"))
			or grn_entry_map.get(grn.name, 0.0)
		)
		aggregated[(s, p.name)]["entry_qty"] += entry_q

	# Physical Paddy = Net Weight (QT) of the weighments (Weigh Bridge Measurement), grouped by PPC.
	# The PPC is the weighment's Party Name (a weighment with a Transit Pass and no Party Name takes the
	# PPC of its pass). The season is the pass season, else the Season Master covering the weighment date.
	rst_mill = {}
	if mill_filter:
		rst_mill = dict(frappe.get_all("RST Details", fields=["name", "mill_name"], as_list=True))
	ppc_by_party: dict[str, object] = {}
	season_by_date: dict[object, str] = {}
	for wbm in frappe.get_all(
		"Weigh Bridge Measurement",
		fields=["name", "party_name", "pass_unique_key", "net_weight", "date", "demo_rst_data"],
	):
		pass_key = (wbm.pass_unique_key or "").strip()
		if mill_filter:
			mill = mill_of_key(pass_key) if pass_key else (rst_mill.get(wbm.demo_rst_data) or "").strip()
			if mill != mill_filter:
				continue
		tp_meta = tp_meta_by_key.get(pass_key, {})
		party = (wbm.party_name or "").strip()
		if party not in ppc_by_party:
			ppc_by_party[party] = resolve_to_ppc_master(party) if party else None
		p = ppc_by_party[party] or tp_meta.get("ppc_doc")
		s = tp_meta.get("season", "")
		if not s and wbm.date:
			day = getdate(wbm.date)
			if day not in season_by_date:
				season_by_date[day] = get_season_for_date(day) or ""
			s = season_by_date[day]
		if not s or not p:
			continue
		aggregated[(s, p.name)]["physical_paddy"] += flt(wbm.net_weight)

	# 7. Render report rows: only PPCs present in PPC Master with Target Allocation > 0 in season
	data = []
	for season in relevant_seasons:
		for p in candidate_ppcs:
			# Only appear if Target Quantity is filled and > 0 for this season
			if ppc_season_totals.get((season, p.name), 0) <= 0:
				continue

			b = aggregated.get((season, p.name), {
				"tp_quantity": 0.0,
				"physical_paddy": 0.0,
				"entry_qty": 0.0,
			})
			tp_qty = flt(b["tp_quantity"], 3)
			physical = flt(b["physical_paddy"], 3)
			entry_qty = flt(b["entry_qty"], 3)
			# Chhatni Quantity = Physical Paddy + Entry Qty - TP Quantity.
			chhatni_qty = flt(physical + entry_qty - tp_qty, 3)

			# Chhatni % = Chhatni Quantity / (TP Quantity - Entry Qty) x 100.
			denom = tp_qty - entry_qty
			if denom > 0:
				chhatni_pct = flt((chhatni_qty / denom) * 100.0, 2)
			else:
				chhatni_pct = 0.0

			label = (
				f"{p.ppc_name}({p.code})"
				if p.code and p.ppc_name and f"({p.code})" not in p.ppc_name
				else (p.title or p.ppc_name or p.code or p.name)
			)

			data.append({
				"season": season,
				"ppc_name": p.name,
				"ppc": label,
				"ppc_display": label,
				"tp_quantity": tp_qty,
				"physical_paddy": physical,
				"entry_qty": entry_qty,
				"chhatni_quantity": chhatni_qty,
				"chhatni_pct": chhatni_pct,
			})

	return data
