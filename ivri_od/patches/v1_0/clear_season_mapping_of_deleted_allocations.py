# Copyright (c) 2026, Profezzo and contributors
"""Season Mapping kept the target of a Target Allocation after it was deleted (e.g. Kharif 2024 and
Rabi 2024 still shown in Abstract Report). Set to 0 the target, agent and chhatni of the mappings
whose Target Allocation was deleted and has none left. Other mappings are not changed."""

import json

import frappe


def execute():
	if not frappe.db.table_exists("Season Mapping"):
		return
	deleted = set()
	for data in frappe.get_all("Deleted Document", filters={"deleted_doctype": "Target Allocation"}, pluck="data"):
		row = json.loads(data or "{}")
		deleted.add((row.get("season"), row.get("ppc_name"), row.get("mill_name")))
	live = {
		(row.season, row.ppc_name, row.mill_name)
		for row in frappe.get_all("Target Allocation", fields=["season", "ppc_name", "mill_name"])
	}
	for mapping in frappe.get_all(
		"Season Mapping", fields=["name", "season", "ppc_name", "mill_name", "season_quantity"]
	):
		key = (mapping.season, mapping.ppc_name, mapping.mill_name)
		if mapping.season_quantity and key in deleted and key not in live:
			frappe.db.set_value(
				"Season Mapping", mapping.name, {"season_quantity": 0, "agent_name": "", "chhatni": 0}
			)
