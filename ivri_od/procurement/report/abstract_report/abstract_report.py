# Copyright (c) 2026, Profezzo and contributors
"""Abstract Report: PPC-wise and Mill-wise matrix reproducing the business Excel structure."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import (
	miller_code_part,
	short_season_code,
)
from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.ppc_pass_metrics import (
	build_pass_quantity_maps,
	completed_quantity_for_pass,
	get_ppc_season_target_map,
	key_matches_mapping,
	make_ppc_resolver,
	ppc_display_name,
	season_label,
)
from ivri_od.procurement.transit_pass_resolve import resolve_ppc_master_name


def execute(filters=None):
	filters = frappe._dict(filters or {})
	relevant_mills = get_relevant_mills(filters)
	columns = get_columns(relevant_mills, filters)
	data = get_data(filters, relevant_mills)
	return columns, data


import re


def _mill_base_company_name(mill: dict) -> str:
	company = (mill.get("company") or mill.get("name") or "").strip()
	base = re.sub(r"[\s\(\[]*(?:raw|boiled)[\s\)\]]*$", "", company, flags=re.IGNORECASE).strip()
	return base or company


def _mill_variant_rank(mill: dict) -> int:
	"""Return 0 for Raw, 1 for Boiled, 2 for other."""
	m_type = (mill.get("type") or "").strip().casefold()
	company = (mill.get("company") or "").strip().casefold()
	name = (mill.get("name") or "").strip().casefold()

	if m_type == "raw" or "(raw)" in company or company.endswith(" raw"):
		return 0
	if m_type == "boiled" or "(boiled)" in company or company.endswith(" boiled"):
		return 1
	if "raw" in company or "raw" in name:
		return 0
	if "boiled" in company or "boiled" in name:
		return 1
	return 2


def sort_mills_by_company_and_type(mills: list[dict]) -> list[dict]:
	"""
	Group mills by base company name, keeping same company mills together,
	and within each company ordering Raw first and Boiled second.
	"""
	if not mills:
		return []

	# Track discovery order of base companies
	company_order: dict[str, int] = {}
	for m in mills:
		base = _mill_base_company_name(m)
		if base not in company_order:
			company_order[base] = len(company_order)

	site_name = (getattr(frappe.local, "site", None) or "").casefold()

	def sort_key(m: dict):
		base = _mill_base_company_name(m)
		is_site_company = 0 if site_name and site_name in base.casefold() else 1
		comp_idx = company_order.get(base, 999)
		var_rank = _mill_variant_rank(m)
		code = (m.get("miller_code") or m.get("name") or "").casefold()
		return (is_site_company, comp_idx, var_rank, code)

	return sorted(mills, key=sort_key)


def get_relevant_mills(filters=None) -> list[dict]:
	"""Dynamically identify relevant mills for the report/filters without hard-coding."""
	filters = frappe._dict(filters or {})
	mill_filter = (filters.get("mill_name") or "").strip()

	# Fetch all active mills from Mill Master
	all_mills = frappe.get_all(
		"Mill Master",
		filters={"is_active": 1},
		fields=["name", "miller_code", "company", "type"],
		order_by="creation asc, name asc",
	)
	if not all_mills:
		all_mills = frappe.get_all(
			"Mill Master",
			fields=["name", "miller_code", "company", "type"],
			order_by="creation asc, name asc",
		)

	# Include any mill present in Season Mapping if not already present
	existing_names = {m.get("name") for m in all_mills}
	mapping_mills = frappe.get_all("Season Mapping", pluck="mill_name", distinct=True)
	for mm in mapping_mills:
		if mm and mm not in existing_names:
			doc = frappe.db.get_value(
				"Mill Master", mm, ["name", "miller_code", "company", "type"], as_dict=True
			)
			if doc:
				all_mills.append(doc)
				existing_names.add(mm)

	if mill_filter:
		filtered = [
			m for m in all_mills
			if m.get("name") == mill_filter or m.get("miller_code") == mill_filter
		]
		if filtered:
			return sort_mills_by_company_and_type(filtered)
		doc = frappe.db.get_value(
			"Mill Master", mill_filter, ["name", "miller_code", "company", "type"], as_dict=True
		)
		if doc:
			return [doc]

	return sort_mills_by_company_and_type(all_mills)


def get_columns(relevant_mills=None, filters=None):
	if relevant_mills is None:
		relevant_mills = get_relevant_mills(filters)

	columns = [
		{
			"label": _("Season"),
			"fieldname": "season",
			"fieldtype": "Link",
			"options": "Season Master",
			"width": 120,
		},
		{
			"label": _("PPC"),
			"fieldname": "ppc_display",
			"fieldtype": "Link",
			"options": "PPC Master",
			"width": 240,
		},
	]

	for mill in relevant_mills:
		code = (mill.get("miller_code") or mill.get("name") or "").strip()
		company = (mill.get("company") or mill.get("name") or "").strip()
		prefix = frappe.scrub(mill.get("name"))

		columns.extend([
			{
				"label": _("Target"),
				"fieldname": f"{prefix}_target",
				"fieldtype": "Float",
				"precision": 3,
				"width": 140,
				"mill_name": company,
				"mill_code": code,
				"mill_id": mill.get("name"),
				"mill_group": True,
			},
			{
				"label": _("Received"),
				"fieldname": f"{prefix}_received",
				"fieldtype": "Float",
				"precision": 3,
				"width": 140,
				"mill_name": company,
				"mill_code": code,
				"mill_id": mill.get("name"),
				"mill_group": True,
			},
			{
				"label": _("Balance"),
				"fieldname": f"{prefix}_balance",
				"fieldtype": "Float",
				"precision": 3,
				"width": 140,
				"mill_name": company,
				"mill_code": code,
				"mill_id": mill.get("name"),
				"mill_group": True,
			},
		])

	columns.extend([
		{
			"label": _("Total Target"),
			"fieldname": "total_target",
			"fieldtype": "Float",
			"precision": 3,
			"width": 140,
		},
		{
			"label": _("Total Received"),
			"fieldname": "total_received",
			"fieldtype": "Float",
			"precision": 3,
			"width": 140,
		},
		{
			"label": _("Total Balance"),
			"fieldname": "total_balance",
			"fieldtype": "Float",
			"precision": 3,
			"width": 140,
		},
	])

	return columns


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_eligible_ppcs_query(doctype, txt, searchfield, start, page_len, filters):
	"""Return only eligible PPCs (present in PPC Master with Target Quantity > 0 in season)."""
	if isinstance(filters, str):
		import json
		try:
			filters = json.loads(filters)
		except Exception:
			filters = {}
	filters = frappe._dict(filters or {})
	season = (filters.get("season") or "").strip()
	mill_name = (filters.get("mill_name") or "").strip()

	ppc_master_rows = frappe.get_all(
		"PPC Master",
		fields=["name", "code", "ppc_name", "title"],
		order_by="ppc_name asc, name asc",
	)
	_, ppc_season_totals = get_ppc_season_target_map(
		season=season if season else None,
		mill_name=mill_name if mill_name else None,
		ppc_master_rows=ppc_master_rows,
	)

	eligible_ppc_names = {
		p_name for (s, p_name), qty in ppc_season_totals.items() if flt(qty) > 0
	}

	txt_lower = (txt or "").strip().casefold()
	results = []
	for p in ppc_master_rows:
		if p.name not in eligible_ppc_names:
			continue
		if txt_lower:
			name_match = txt_lower in p.name.casefold()
			code_match = p.code and txt_lower in p.code.casefold()
			title_match = p.ppc_name and txt_lower in p.ppc_name.casefold()
			if not (name_match or code_match or title_match):
				continue
		label = f"{p.ppc_name}({p.code})" if p.code and p.ppc_name else (p.ppc_name or p.name)
		results.append((p.name, label))

	start = int(start or 0)
	page_len = int(page_len or 20)
	return results[start : start + page_len]


def get_data(filters, relevant_mills=None):
	filters = frappe._dict(filters or {})
	if relevant_mills is None:
		relevant_mills = get_relevant_mills(filters)

	season_filter = (filters.get("season") or "").strip()
	ppc_filter = (filters.get("ppc_name") or filters.get("ppc") or "").strip()

	# 1. Authoritative PPC master list from PPC Master DocType
	ppc_master_rows = frappe.get_all(
		"PPC Master",
		fields=["name", "code", "ppc_name", "title"],
		order_by="ppc_name asc, name asc",
	)
	resolve_to_ppc_master = make_ppc_resolver(ppc_master_rows)

	if ppc_filter:
		filter_doc = resolve_to_ppc_master(ppc_filter)
		candidate_ppcs = [filter_doc] if filter_doc else []
	else:
		candidate_ppcs = ppc_master_rows

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
			for s in frappe.get_all("PPAS Transit Pass", pluck="season", distinct=True):
				if s:
					discovered.add(resolve_season_master_name(s) or s.strip())
			relevant_seasons = sorted(list(discovered))

	# 2. Fetch Target Allocations in bulk dynamically at runtime
	target_map, ppc_season_totals = get_ppc_season_target_map(
		season=season_filter if season_filter else None,
		mill_name=filters.get("mill_name"),
		ppc_master_rows=ppc_master_rows,
	)

	# 3. Index completed pass quantities using canonical key_matches_mapping
	maps = build_pass_quantity_maps()
	received_by_key = maps["received_by_key"]
	tp_qty_by_key = maps["tp_qty_by_key"]

	passes = frappe.get_all(
		"PPAS Transit Pass",
		fields=["name", "pass_unique_key", "season", "ppc", "miller", "quantity"],
	)

	passes_by_mill_season = defaultdict(list)
	for tp in passes:
		key = (tp.pass_unique_key or tp.name or "").strip()
		if not key:
			continue
		parts = key.split("-")
		if len(parts) < 4:
			continue
		m_code = miller_code_part(parts[0]).casefold()
		s_code = parts[-2].casefold()
		recv = received_by_key.get(key, 0)
		tp_q = tp_qty_by_key.get(key, 0) or flt(tp.quantity)
		comp = completed_quantity_for_pass(recv, tp_q)
		passes_by_mill_season[(m_code, s_code)].append((key, comp))

	# 4. Render rows: only PPCs present in PPC Master with Target Allocation > 0 in season
	data = []
	for season in relevant_seasons:
		season_code = short_season_code(season)
		for p in candidate_ppcs:
			# Only appear if Target Quantity is filled and > 0 for this season
			if ppc_season_totals.get((season, p.name), 0) <= 0:
				continue

			ppc_label = (
				f"{p.ppc_name}({p.code})"
				if p.code and p.ppc_name and f"({p.code})" not in p.ppc_name
				else (p.title or p.ppc_name or p.code or p.name)
			)

			row = {
				"season": season,
				"ppc_name": p.name,
				"ppc_display": ppc_label,
				"ppc": ppc_label,
			}

			for mill in relevant_mills:
				mill_code = mill.get("miller_code") or mill.get("name") or ""
				mill_company = mill.get("company") or mill.get("name") or ""
				prefix = frappe.scrub(mill.get("name"))

				assigned = target_map.get((season, p.name, mill.get("name")), 0.0)

				candidate_passes = passes_by_mill_season.get(
					(mill_code.casefold(), season_code.casefold()), []
				)
				completed = 0.0
				for key, comp in candidate_passes:
					if key_matches_mapping(key, mill_code, p.code or "", p.name, season_code):
						completed += comp

				remaining = flt(max(assigned - completed, 0.0), 3)

				row[f"{prefix}_target"] = flt(assigned, 3)
				row[f"{prefix}_received"] = flt(completed, 3)
				row[f"{prefix}_balance"] = remaining
				row[f"{prefix}_mill_name"] = mill_company
				row[f"{prefix}_mill_code"] = mill_code

			row["total_target"] = flt(
				sum(row[f"{frappe.scrub(m.get('name'))}_target"] for m in relevant_mills), 3
			)
			row["total_received"] = flt(
				sum(row[f"{frappe.scrub(m.get('name'))}_received"] for m in relevant_mills), 3
			)
			row["total_balance"] = flt(
				sum(row[f"{frappe.scrub(m.get('name'))}_balance"] for m in relevant_mills), 3
			)
			data.append(row)

	return data
