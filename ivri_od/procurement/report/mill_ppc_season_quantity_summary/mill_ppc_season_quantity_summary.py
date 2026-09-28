# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import (
	miller_code_part,
	short_season_code,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Season"), "fieldname": "season", "fieldtype": "Link", "options": "Season Master", "width": 130},
		{"label": _("Mill Name (Code)"), "fieldname": "mill_display", "fieldtype": "Data", "width": 220},
		{"label": _("PPC Name (Code)"), "fieldname": "ppc_display", "fieldtype": "Data", "width": 230},
		{"label": _("Assigned Quantity (QT)"), "fieldname": "assigned_quantity", "fieldtype": "Float", "precision": 3, "width": 170},
		{"label": _("Completed Quantity (QT)"), "fieldname": "completed_quantity", "fieldtype": "Float", "precision": 3, "width": 180},
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

	passes = frappe.get_all(
		"PPAS Transit Pass",
		fields=["name", "pass_unique_key", "season", "ppc", "miller", "quantity"],
	)
	grns = frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2]},
		fields=["pass_unique_key", "tp_quantity", "net_weight"],
	)
	grn_quantity_by_key = {}
	for grn in grns:
		key = _normalize(grn.pass_unique_key)
		if not key:
			continue
		# A load is complete only up to its TP allocation, even when the
		# weighbridge net quantity is higher.
		grn_quantity_by_key[key] = grn_quantity_by_key.get(key, 0) + min(
			max(flt(grn.tp_quantity), 0), max(flt(grn.net_weight), 0)
		)

	data = []
	for mapping in mappings:
		mill_code = frappe.db.get_value("Mill Master", mapping.mill_name, "miller_code") or ""
		ppc_code = frappe.db.get_value("PPC Master", mapping.ppc_name, "code") or ""
		season_code = short_season_code(_season_label(mapping.season, mapping.season_year))
		completed = 0.0
		for tp in passes:
			key = (tp.pass_unique_key or tp.name or "").strip()
			if not key or not _key_matches_mapping(key, mill_code, ppc_code, mapping.ppc_name, season_code):
				continue
			completed += grn_quantity_by_key.get(_normalize(key), 0)

		data.append(
			{
				"season": mapping.season,
				"mill_display": f"{mapping.mill_name} ({mill_code})" if mill_code else mapping.mill_name,
				"ppc_display": f"{_ppc_name(mapping.ppc_name)} ({ppc_code})" if ppc_code else _ppc_name(mapping.ppc_name),
				"assigned_quantity": flt(mapping.season_quantity),
				"completed_quantity": completed,
			}
		)
	return data


def _season_label(season, year):
	details = frappe.db.get_value("Season Master", season, ["crop_season", "year"], as_dict=True)
	if details:
		return f"{details.crop_season} {details.year}"
	return f"{season} {year or ''}".strip()


def _ppc_name(ppc_link):
	return frappe.db.get_value("PPC Master", ppc_link, "ppc_name") or ppc_link


def _key_matches_mapping(key, mill_code, ppc_code, ppc_link, season_code):
	parts = key.split("-")
	if len(parts) < 4:
		return False
	if mill_code and miller_code_part(parts[0]).casefold() != mill_code.casefold():
		return False
	if parts[-2].casefold() != season_code.casefold():
		return False
	ppc_part = "-".join(parts[1:-2])
	if "(" in ppc_part and ppc_part.endswith(")"):
		name, code = ppc_part.rsplit("(", 1)
		code = code[:-1]
		return code.casefold() == (ppc_code or "").casefold() or _normalize(name) == _normalize(_ppc_name(ppc_link))
	return _normalize(ppc_part) in {_normalize(ppc_link), _normalize(_ppc_name(ppc_link)), _normalize(ppc_code)}


def _normalize(value):
	return re.sub(r"\s+", "", value or "").casefold()
