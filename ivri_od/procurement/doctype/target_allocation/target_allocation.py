# Copyright (c) 2026, Profezzo and contributors

import frappe
from frappe.model.document import Document
from frappe.utils import flt


def get_latest_chutney_for_ppc_mill(
	ppc_name: str | None, mill_name: str | None, season: str | None = None
) -> dict:
	if not ppc_name or not mill_name:
		return {}

	filters = {"ppc_name": ppc_name, "mill_name": mill_name}
	if (season or "").strip():
		filters["season"] = season.strip()

	rows = frappe.get_all(
		"Chhatni Assign",
		filters=filters,
		fields=[
			"name",
			"season",
			"chutney_quantity_kg_per_quintal",
			"chutney_percentage",
		],
		order_by="modified desc",
		limit=1,
	)
	return rows[0] if rows else {}


class TargetAllocation(Document):
	def validate(self):
		self.target_quantity = flt(self.target_quantity)
		self.chhatni = flt(self.chhatni)
		self.validate_agent_details()
		self.sync_agent_name()
		self.validate_unique_ppc_mill_season()
		self.set_latest_chutney_from_assign()

	def validate_agent_details(self):
		seen = set()
		for row in self.get("agent_details") or []:
			if not (row.agent_name or "").strip():
				continue
			agent_name = row.agent_name.strip()
			if agent_name in seen:
				frappe.throw(
					frappe._("Agent '{0}' is added more than once in Agent Details.").format(agent_name)
				)
			seen.add(agent_name)

	def sync_agent_name(self):
		agent_rows = [
			row.agent_name.strip()
			for row in (self.get("agent_details") or [])
			if (row.agent_name or "").strip()
		]
		if agent_rows:
			if not (self.agent_name or "").strip() or self.agent_name.strip() not in agent_rows:
				self.agent_name = agent_rows[0]
		elif (self.agent_name or "").strip() and (
			self.is_new() or not frappe.db.exists("Target Allocation Agent", {"parent": self.name})
		):
			self.append("agent_details", {"agent_name": self.agent_name.strip()})
		elif not agent_rows:
			self.agent_name = ""

	def validate_unique_ppc_mill_season(self):
		if not (self.ppc_name and self.mill_name and self.season):
			return

		existing = frappe.db.exists(
			"Target Allocation",
			{
				"ppc_name": self.ppc_name,
				"mill_name": self.mill_name,
				"season": self.season,
				"name": ("!=", self.name),
			},
		)
		if existing:
			frappe.throw(
				frappe._(
					"Target Allocation already exists for PPC {0}, Mill {1}, and Season {2}: {3}. Edit that record instead of creating another."
				).format(self.ppc_name, self.mill_name, self.season, existing)
			)

	def on_update(self):
		sync_season_mappings_from_allocation(self.season, self.ppc_name, self.mill_name)

	def after_delete(self):
		sync_season_mappings_from_allocation(self.season, self.ppc_name, self.mill_name)

	def set_latest_chutney_from_assign(self):
		data = get_latest_chutney_for_ppc_mill(self.ppc_name, self.mill_name, self.season)
		if not data:
			self.latest_chutney_assign = None
			self.latest_chutney_season = None
			self.latest_chutney_kg_per_quintal = 0
			self.latest_chutney_percentage = 0
			return

		self.latest_chutney_assign = data.name
		self.latest_chutney_season = data.season
		self.latest_chutney_kg_per_quintal = flt(data.chutney_quantity_kg_per_quintal)
		self.latest_chutney_percentage = flt(data.chutney_percentage)

		# Default Chhatni from assign when not set on this Target Allocation.
		if not flt(self.chhatni):
			self.chhatni = flt(data.chutney_quantity_kg_per_quintal)


@frappe.whitelist()
def fetch_latest_chutney(ppc_name, mill_name, season=None):
	return get_latest_chutney_for_ppc_mill(ppc_name, mill_name, season)


def sync_season_mappings_from_allocation(season, ppc_name, mill_name):
	"""Push Target Allocation quantity and agent into matching Season Mapping rows."""
	from ivri_od.procurement.doctype.season_mapping.season_mapping import (
		get_target_allocation_summary,
	)

	season = (season or "").strip()
	ppc_name = (ppc_name or "").strip()
	mill_name = (mill_name or "").strip()
	if not (season and ppc_name and mill_name):
		return

	summary = get_target_allocation_summary(season, ppc_name, mill_name)
	if not summary:
		return

	values = {
		"season_quantity": summary["target_quantity"],
		"agent_name": summary.get("agent_name") or "",
		"chhatni": flt(summary.get("chhatni")),
	}
	names = frappe.get_all(
		"Season Mapping",
		filters={"season": season, "ppc_name": ppc_name, "mill_name": mill_name},
		pluck="name",
	)
	if names:
		for name in names:
			frappe.db.set_value("Season Mapping", name, values, update_modified=True)
		return

	mapping = frappe.new_doc("Season Mapping")
	mapping.season = season
	mapping.ppc_name = ppc_name
	mapping.mill_name = mill_name
	mapping.season_quantity = values["season_quantity"]
	mapping.agent_name = values["agent_name"]
	mapping.chhatni = values["chhatni"]
	mapping.insert(ignore_permissions=True)
