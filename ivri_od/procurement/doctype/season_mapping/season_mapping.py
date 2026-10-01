# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import short_season_code
from ivri_od.procurement.doctype.season_master.season_master import get_or_create_season_master


def get_target_allocation_summary(season, ppc_name, mill_name) -> dict:
	"""Quantity and agent entered on Target Allocation for this season, PPC, and mill."""
	season = (season or "").strip()
	ppc_name = (ppc_name or "").strip()
	mill_name = (mill_name or "").strip()
	if not (season and ppc_name and mill_name):
		return {}

	rows = frappe.get_all(
		"Target Allocation",
		filters={"season": season, "ppc_name": ppc_name, "mill_name": mill_name},
		fields=["target_quantity", "agent_name", "chhatni"],
	)
	if not rows:
		return {}

	agents = {(row.agent_name or "").strip() for row in rows if (row.agent_name or "").strip()}
	chhatni_values = [flt(row.chhatni) for row in rows if flt(row.chhatni)]
	return {
		"target_quantity": flt(sum(flt(row.target_quantity) for row in rows)),
		"agent_name": next(iter(agents)) if len(agents) == 1 else "",
		"chhatni": chhatni_values[0] if chhatni_values else 0,
	}


class SeasonMapping(Document):
	def validate(self):
		self.sync_season_year_from_master()
		self.fetch_from_target_allocation()
		self.calculate_collection_point_quantities()

		existing = frappe.db.exists(
			"Season Mapping",
			{
				"mill_name": self.mill_name,
				"ppc_name": self.ppc_name,
				"season": self.season,
				"season_year": self.season_year,
				"name": ("!=", self.name),
			},
		)
		if existing:
			frappe.throw(
				f"Season Mapping already exists for this Mill, PPC, Season and Year: {existing}"
			)

	def fetch_from_target_allocation(self):
		summary = get_target_allocation_summary(self.season, self.ppc_name, self.mill_name)
		if not summary:
			self.chhatni = 0
			return
		self.season_quantity = summary["target_quantity"]
		self.agent_name = summary.get("agent_name") or ""
		self.chhatni = flt(summary.get("chhatni"))

	def calculate_collection_point_quantities(self):
		paddy_procured = get_grn_paddy_procured(self.season, self.ppc_name, self.mill_name)
		for row in self.collection_point_details or []:
			row.paddy_procured_till_date = flt(paddy_procured * flt(row.paddy_proportion) / 100, 3)
			row.rice_due_till_date = flt(row.paddy_procured_till_date) / 100 * flt(self.rice_yield)
			row.remaining_balance = (
				flt(self.season_quantity)
				/ 100
				* flt(self.rice_yield)
				/ 100
				* flt(row.paddy_proportion)
				- flt(row.rice_due_till_date)
			)

	def sync_season_year_from_master(self):
		if not self.season:
			return

		if not frappe.db.exists("Season Master", self.season):
			legacy_crop = (self.season or "").strip()
			legacy_year = (self.season_year or "").strip()
			if legacy_crop in ("Kharif", "Rabi") and legacy_year:
				self.season = get_or_create_season_master(legacy_crop, legacy_year) or self.season
			else:
				frappe.throw(
					frappe._("Season {0} was not found in Season Master").format(self.season)
				)

		year = frappe.db.get_value("Season Master", self.season, "year")
		if year:
			self.season_year = str(year).strip()


@frappe.whitelist()
def fetch_target_allocation(season, ppc_name, mill_name):
	return get_target_allocation_summary(season, ppc_name, mill_name)


def get_chhatni_from_season_mapping(season, ppc_name, mill_name) -> float:
	season = (season or "").strip()
	ppc_name = (ppc_name or "").strip()
	mill_name = (mill_name or "").strip()
	if not (season and ppc_name and mill_name):
		return 0.0
	value = frappe.db.get_value(
		"Season Mapping",
		{"season": season, "ppc_name": ppc_name, "mill_name": mill_name},
		"chhatni",
	)
	return flt(value) if value is not None else 0.0


@frappe.whitelist()
def fetch_chhatni_from_season_mapping(season, ppc_name, mill_name):
	return get_chhatni_from_season_mapping(season, ppc_name, mill_name)


@frappe.whitelist()
def get_grn_paddy_procured(season, ppc_name, mill_name):
	"""Sum GRN net paddy by matching season/PPC/mill, capped at each TP quantity."""
	if not (season and ppc_name and mill_name):
		return 0.0
	if not frappe.has_permission("Season Mapping", "read"):
		frappe.throw(frappe._("Not permitted to read Season Mapping."), frappe.PermissionError)

	season_master = frappe.db.get_value(
		"Season Master", season, ["crop_season", "year"], as_dict=True
	)
	if not season_master:
		return 0.0
	season_code = short_season_code(f"{season_master.crop_season} {season_master.year}")
	mill_code = frappe.db.get_value("Mill Master", mill_name, "miller_code") or mill_name
	ppc = frappe.db.get_value("PPC Master", ppc_name, ["ppc_name", "code"], as_dict=True)
	if not ppc:
		return 0.0
	ppc_aliases = {
		_normalize(ppc_name),
		_normalize(ppc.ppc_name),
		_normalize(ppc.code),
		_normalize(f"{ppc.ppc_name}({ppc.code})"),
	}

	grns = frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2]},
		fields=["name", "pass_unique_key", "tp_quantity", "net_weight"],
	)
	pass_limits = {}
	grn_net_by_pass = {}
	grn_pass_by_name = {}
	for grn in grns:
		key = (grn.pass_unique_key or "").strip()
		parts = key.split("-")
		if len(parts) < 4:
			continue
		key_ppc = "-".join(parts[1:-2])
		if _normalize(parts[0]) != _normalize(mill_code):
			continue
		if _normalize(parts[-2]) != _normalize(season_code):
			continue
		if _normalize(key_ppc) not in ppc_aliases:
			continue
		grn_pass_by_name[grn.name] = key
		grn_net_by_pass[key] = grn_net_by_pass.get(key, 0.0) + max(flt(grn.net_weight), 0.0)
		pass_limits[key] = max(pass_limits.get(key, 0.0), max(flt(grn.tp_quantity), 0.0))

	entry_quantity_by_pass = {}
	seen_entries = set()
	if grn_pass_by_name:
		grn_entry_rows = frappe.get_all(
			"GRN Entry Detail",
			filters={
				"parent": ["in", list(grn_pass_by_name)],
				"parenttype": "GRN Note",
				"parentfield": "entry_details",
			},
			fields=["name", "parent", "entry", "entry_quantity"],
		)
		for row in grn_entry_rows:
			key = grn_pass_by_name.get(row.parent)
			if not key:
				continue
			entry_id = row.entry or f"{row.parent}:{row.name}"
			unique_entry = (key, entry_id)
			if unique_entry in seen_entries:
				continue
			seen_entries.add(unique_entry)
			entry_quantity_by_pass[key] = entry_quantity_by_pass.get(key, 0.0) + max(
				flt(row.entry_quantity), 0.0
			)

	return flt(
		sum(
			min(
				net_weight + entry_quantity_by_pass.get(key, 0.0),
				pass_limits.get(key, 0.0),
			)
			for key, net_weight in grn_net_by_pass.items()
		),
		3,
	)


def _normalize(value):
	return "".join((value or "").split()).casefold()
