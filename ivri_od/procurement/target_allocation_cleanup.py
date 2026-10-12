# Copyright (c) 2026, Profezzo and contributors
"""Utility to audit and clean up invalid/random testing PPC records from Target Allocation."""

from __future__ import annotations

import frappe
from frappe.utils import flt

from ivri_od.procurement.transit_pass_resolve import resolve_ppc_master_name


def audit_and_cleanup_invalid_allocations(dry_run: bool = False) -> list[dict]:
	"""
	Audit all Target Allocation and Season Mapping records.
	Identify records where the PPC does NOT exist in PPC Master.
	Log before deleting and delete only confirmed invalid records.
	"""
	deleted_records = []
	master_rows = frappe.get_all("PPC Master", fields=["name", "code", "ppc_name"])
	master_names = {r.name for r in master_rows}
	master_codes = {r.code for r in master_rows if r.code}
	master_names_cf = {r.ppc_name.strip().casefold() for r in master_rows if r.ppc_name}

	def is_valid_ppc(ppc_val: str | None) -> bool:
		raw = (ppc_val or "").strip()
		if not raw:
			return False
		if raw in master_names or raw in master_codes:
			return True
		if "(" in raw and raw.endswith(")"):
			code = raw.rsplit("(", 1)[1][:-1].strip()
			if code in master_codes or code in master_names:
				return True
		if raw.casefold() in master_names_cf:
			return True
		resolved = resolve_ppc_master_name(raw)
		if resolved and (resolved in master_names or resolved in master_codes):
			return True
		return False

	# 1. Inspect Target Allocation
	if frappe.db.table_exists("Target Allocation"):
		ta_records = frappe.get_all(
			"Target Allocation",
			fields=["name", "season", "ppc_name", "mill_name", "target_quantity"],
		)
		for r in ta_records:
			if not is_valid_ppc(r.ppc_name):
				entry = {
					"doctype": "Target Allocation",
					"id": r.name,
					"ppc_value": r.ppc_name,
					"season": r.season,
					"mill_name": r.mill_name,
					"target_quantity": flt(r.target_quantity),
				}
				deleted_records.append(entry)
				print(
					f"[AUDIT] Invalid Target Allocation found: ID={r.name}, PPC={r.ppc_name}, "
					f"Season={r.season}, Target Quantity={r.target_quantity}"
				)
				if not dry_run:
					frappe.delete_doc("Target Allocation", r.name, force=True, ignore_permissions=True)
					print(f"[CLEANUP] Deleted Target Allocation record: {r.name}")

	# 2. Inspect Season Mapping
	if frappe.db.table_exists("Season Mapping"):
		sm_records = frappe.get_all(
			"Season Mapping",
			fields=["name", "season", "ppc_name", "mill_name", "season_quantity"],
		)
		for r in sm_records:
			if not is_valid_ppc(r.ppc_name):
				entry = {
					"doctype": "Season Mapping",
					"id": r.name,
					"ppc_value": r.ppc_name,
					"season": r.season,
					"mill_name": r.mill_name,
					"target_quantity": flt(r.season_quantity),
				}
				deleted_records.append(entry)
				print(
					f"[AUDIT] Invalid Season Mapping found: ID={r.name}, PPC={r.ppc_name}, "
					f"Season={r.season}, Season Quantity={r.season_quantity}"
				)
				if not dry_run:
					frappe.delete_doc("Season Mapping", r.name, force=True, ignore_permissions=True)
					print(f"[CLEANUP] Deleted Season Mapping record: {r.name}")

	if not deleted_records:
		print("[AUDIT] No invalid Target Allocation or Season Mapping records found. All existing records are valid.")

	return deleted_records


def run():
	audit_and_cleanup_invalid_allocations(dry_run=False)
