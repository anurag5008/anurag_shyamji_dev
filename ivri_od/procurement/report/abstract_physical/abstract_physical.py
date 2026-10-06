# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.ppc_pass_metrics import (
	build_pass_quantity_maps,
	effective_tp_quantity_for_physical_abstract,
	ppc_display_name,
	ppc_link_for_pass_key,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("PACS Name"), "fieldname": "pacs_name", "fieldtype": "Data", "width": 220},
		{
			"label": _("PPC"),
			"fieldname": "ppc_name",
			"fieldtype": "Link",
			"options": "PPC Master",
			"width": 140,
		},
		{
			"label": _("TP Quantity (QT)"),
			"fieldname": "tp_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"label": _("Physical Paddy (QT)"),
			"fieldname": "physical_paddy",
			"fieldtype": "Float",
			"precision": 3,
			"width": 140,
		},
		{
			"label": _("Entry Qty (QT)"),
			"fieldname": "entry_qty",
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{
			"label": _("Chhatni Quantity (QT)"),
			"fieldname": "chhatni_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Chhatni %"),
			"fieldname": "chhatni_pct",
			"fieldtype": "Percent",
			"precision": 2,
			"width": 100,
		},
	]


def get_data(filters):
	maps = build_pass_quantity_maps()
	keys = set(maps["physical_by_key"]) | set(maps["received_by_key"]) | set(maps["entry_by_key"])
	if not keys:
		return []

	ppc_agg: dict[str, dict] = {}
	season_filter = (filters.get("season") or "").strip()
	ppc_filter = (filters.get("ppc_name") or "").strip()

	for key in keys:
		ppc_link = ppc_link_for_pass_key(key, maps["ppc_text_by_key"])
		if not ppc_link:
			continue
		if ppc_filter and ppc_link != ppc_filter:
			continue
		if season_filter and not _pass_in_season(key, season_filter):
			continue

		bucket = ppc_agg.setdefault(
			ppc_link,
			{
				"ppc_name": ppc_link,
				"pacs_names": set(),
				"tp_quantity": 0.0,
				"physical_paddy": 0.0,
				"entry_qty": 0.0,
			},
		)
		received = flt(maps["received_by_key"].get(key))
		tp_qty = flt(maps["tp_qty_by_key"].get(key))
		physical = flt(maps["physical_by_key"].get(key))
		entry_qty = flt(maps["entry_by_key"].get(key))

		bucket["physical_paddy"] += physical
		bucket["entry_qty"] += entry_qty
		bucket["tp_quantity"] += effective_tp_quantity_for_physical_abstract(
			entry_qty, received, tp_qty
		)
		pacs = (maps["pacs_by_key"].get(key) or "").strip()
		if pacs:
			bucket["pacs_names"].add(pacs)

	data = []
	for ppc_link, row in sorted(ppc_agg.items(), key=lambda x: ppc_display_name(x[0])):
		tp_sum = flt(row["tp_quantity"], 3)
		physical = flt(row["physical_paddy"], 3)
		chhatni_qty = flt(max(physical - tp_sum, 0), 3)
		chhatni_pct = flt(chhatni_qty / tp_sum * 100, 2) if tp_sum > 0 else 0
		pacs_label = ", ".join(sorted(row["pacs_names"])) if row["pacs_names"] else ppc_display_name(ppc_link)

		data.append(
			{
				"pacs_name": pacs_label,
				"ppc_name": ppc_link,
				"tp_quantity": tp_sum,
				"physical_paddy": physical,
				"entry_qty": flt(row["entry_qty"], 3),
				"chhatni_quantity": chhatni_qty,
				"chhatni_pct": chhatni_pct,
			}
		)
	return data


def _pass_in_season(pass_key: str, season_master: str) -> bool:
	"""Rough match: season code in pass key vs Season Master label."""
	from ivri_od.procurement.ppc_pass_metrics import season_label
	from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import short_season_code

	year = frappe.db.get_value("Season Master", season_master, "year")
	code = short_season_code(season_label(season_master, year))
	parts = (pass_key or "").split("-")
	if len(parts) < 4:
		return True
	return parts[-2].casefold() == code.casefold()
