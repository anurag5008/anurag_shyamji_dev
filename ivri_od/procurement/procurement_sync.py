# Copyright (c) 2026, Profezzo and contributors
"""Keep Season Mapping and report rollups aligned with WBM / GRN / Entry activity."""

from __future__ import annotations

import frappe
from frappe.utils import flt

from ivri_od.procurement.doctype.season_mapping.season_mapping import get_target_allocation_summary
from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.ppc_pass_metrics import _ppc_text_from_pass_unique_key
from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name, resolve_ppc_master_name


def procurement_dimensions_from_pass_key(pass_unique_key: str) -> dict | None:
	"""Resolve Season Mapping keys (season, ppc_name, mill_name) from a transit pass key."""
	key = (pass_unique_key or "").strip()
	parts = key.split("-")
	if len(parts) < 4:
		return None

	mill_name = resolve_mill_master_name(key, parts[0]) or (parts[0] or "").strip()
	ppc_part = "-".join(parts[1:-2]).strip() or _ppc_text_from_pass_unique_key(key)
	ppc_name = resolve_ppc_master_name(ppc_part) or resolve_ppc_master_name(
		_ppc_text_from_pass_unique_key(key)
	)
	season = resolve_season_master_name(parts[-2])

	if not mill_name or not ppc_name or not season:
		return None
	if not frappe.db.exists("Mill Master", mill_name):
		return None
	if not frappe.db.exists("PPC Master", ppc_name):
		return None
	if not frappe.db.exists("Season Master", season):
		return None

	return {"season": season, "ppc_name": ppc_name, "mill_name": mill_name}


def sync_procurement_from_pass(pass_unique_key: str) -> str | None:
	"""
	Ensure Season Mapping exists for this pass and refresh procured child rows.
	Called when WBM / GRN / Entry changes so Abstract and Season Mapping stay in sync.
	"""
	key = (pass_unique_key or "").strip()
	if not key:
		return None

	dims = procurement_dimensions_from_pass_key(key)
	if not dims:
		return None

	mapping_name = frappe.db.get_value(
		"Season Mapping",
		{"season": dims["season"], "ppc_name": dims["ppc_name"], "mill_name": dims["mill_name"]},
		"name",
	)
	if mapping_name:
		_refresh_season_mapping(mapping_name)
		return mapping_name

	summary = get_target_allocation_summary(dims["season"], dims["ppc_name"], dims["mill_name"])
	doc = frappe.new_doc("Season Mapping")
	doc.season = dims["season"]
	doc.ppc_name = dims["ppc_name"]
	doc.mill_name = dims["mill_name"]
	doc.season_quantity = flt(summary.get("target_quantity")) if summary else 0
	doc.agent_name = (summary or {}).get("agent_name") or ""
	doc.chhatni = flt((summary or {}).get("chhatni")) if summary else 0
	doc.flags.from_procurement_sync = True
	doc.insert(ignore_permissions=True)
	return doc.name


def _refresh_season_mapping(mapping_name: str) -> None:
	doc = frappe.get_doc("Season Mapping", mapping_name)
	doc.flags.from_procurement_sync = True
	doc.fetch_from_target_allocation()
	doc.calculate_collection_point_quantities()
	doc.save(ignore_permissions=True)


def sync_all_procurement_season_mappings() -> int:
	"""Backfill Season Mapping rows from government GRN and WBM pass keys."""
	keys: set[str] = set()
	for row in frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2], "is_local_procurement": 0},
		fields=["pass_unique_key"],
	):
		key = (row.pass_unique_key or "").strip()
		if key:
			keys.add(key)

	for row in frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"is_farmer_or_agent": 0},
		fields=["pass_unique_key", "net_weight", "quality_test"],
	):
		if (row.quality_test or "") == "Rejected":
			continue
		key = (row.pass_unique_key or "").strip()
		if key and flt(row.net_weight) > 0:
			keys.add(key)

	for row in frappe.get_all("Entry", fields=["pass_unique_key"]):
		key = (row.pass_unique_key or "").strip()
		if key:
			keys.add(key)

	created = 0
	for key in keys:
		dims = procurement_dimensions_from_pass_key(key)
		if not dims:
			continue
		existed = frappe.db.exists("Season Mapping", dims)
		sync_procurement_from_pass(key)
		if not existed:
			created += 1
	return created
