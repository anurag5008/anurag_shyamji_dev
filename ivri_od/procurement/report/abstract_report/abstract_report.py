# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.ppc_pass_metrics import (
	build_pass_quantity_maps,
	completed_quantity_for_pass,
	key_matches_mapping,
	mill_display_name,
	ppc_display_name,
	season_label,
)
from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import short_season_code


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
			"width": 120,
		},
		{
			"label": _("Mill Name"),
			"fieldname": "mill_name",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": _("Mill Code"),
			"fieldname": "mill_code",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("PPC Name"),
			"fieldname": "ppc_display",
			"fieldtype": "Data",
			"width": 220,
		},
		{
			"label": _("Assigned Quantity (QT)"),
			"fieldname": "assigned_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Received Quantity (QT)"),
			"fieldname": "completed_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
		{
			"label": _("Balance Quantity (QT)"),
			"fieldname": "balance_quantity",
			"fieldtype": "Float",
			"precision": 3,
			"width": 150,
		},
	]


def get_data(filters):
	conditions = {}
	for fieldname in ("season", "ppc_name", "mill_name"):
		if filters.get(fieldname):
			conditions[fieldname] = filters[fieldname]

	mappings = frappe.get_all(
		"Season Mapping",
		filters=conditions,
		fields=["season", "season_year", "ppc_name", "mill_name", "season_quantity"],
		order_by="season asc, mill_name asc, ppc_name asc",
	)
	if not mappings:
		return []

	maps = build_pass_quantity_maps()
	received_by_key = maps["received_by_key"]
	tp_qty_by_key = maps["tp_qty_by_key"]

	passes = frappe.get_all(
		"PPAS Transit Pass",
		fields=["name", "pass_unique_key", "season", "ppc", "miller", "quantity"],
	)

	data = []
	for mapping in mappings:
		mill_code = frappe.db.get_value("Mill Master", mapping.mill_name, "miller_code") or mapping.mill_name
		ppc_code = frappe.db.get_value("PPC Master", mapping.ppc_name, "code") or ""
		season_code = short_season_code(season_label(mapping.season, mapping.season_year))
		completed = 0.0
		for tp in passes:
			key = (tp.pass_unique_key or tp.name or "").strip()
			if not key or not key_matches_mapping(
				key, mill_code, ppc_code, mapping.ppc_name, season_code
			):
				continue
			received = received_by_key.get(key, 0)
			tp_qty = tp_qty_by_key.get(key, 0) or flt(tp.quantity)
			completed += completed_quantity_for_pass(received, tp_qty)

		assigned = flt(mapping.season_quantity)
		data.append(
			{
				"season": mapping.season,
				"mill_name": mill_display_name(mapping.mill_name),
				"mill_code": mill_code,
				"ppc_display": ppc_display_name(mapping.ppc_name),
				"assigned_quantity": assigned,
				"completed_quantity": completed,
				"balance_quantity": flt(assigned - completed, 3),
			}
		)
	return data
