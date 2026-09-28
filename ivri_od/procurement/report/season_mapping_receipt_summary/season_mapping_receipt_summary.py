# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import miller_code_part


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Season"), "fieldname": "season", "fieldtype": "Link", "options": "Season Master", "width": 130},
		{"label": _("Year"), "fieldname": "season_year", "fieldtype": "Data", "width": 80},
		{"label": _("PPC Name (Code)"), "fieldname": "ppc_display", "fieldtype": "Data", "width": 220},
		{"label": _("Mill Name (Number)"), "fieldname": "mill_display", "fieldtype": "Data", "width": 220},
		{"label": _("Season Mapping Quantity"), "fieldname": "season_quantity", "fieldtype": "Float", "precision": 3, "width": 160},
		{"label": _("Quantity Received (WBM Net)"), "fieldname": "quantity_received", "fieldtype": "Float", "precision": 3, "width": 180},
		{"label": _("RST Count"), "fieldname": "rst_count", "fieldtype": "Int", "width": 100},
		{"label": _("Transit Pass Count"), "fieldname": "transit_pass_count", "fieldtype": "Int", "width": 140},
	]


def get_data(filters):
	mapping_filters = {}
	for fieldname in ("season", "ppc_name", "mill_name"):
		if filters.get(fieldname):
			mapping_filters[fieldname] = filters[fieldname]

	mappings = frappe.get_all(
		"Season Mapping",
		filters=mapping_filters,
		fields=["name", "season", "season_year", "ppc_name", "mill_name", "season_quantity"],
		order_by="season asc, ppc_name asc, mill_name asc",
	)
	transit_passes = frappe.get_all(
		"PPAS Transit Pass",
		fields=["name", "pass_unique_key", "season", "ppc", "miller"],
	)
	wbm_by_pass = _get_wbm_by_pass()

	data = []
	for mapping in mappings:
		mill_code = frappe.db.get_value("Mill Master", mapping.mill_name, "miller_code") or ""
		mill_name = frappe.db.get_value("Mill Master", mapping.mill_name, "company") or mapping.mill_name
		ppc = frappe.db.get_value(
			"PPC Master", mapping.ppc_name, ["ppc_name", "code"], as_dict=True
		)
		ppc_display = (
			f"{ppc.ppc_name} ({ppc.code})" if ppc and ppc.code else (ppc.ppc_name if ppc else mapping.ppc_name)
		)
		mill_display = f"{mill_name} ({mill_code})" if mill_code else mill_name
		season_aliases = _season_aliases(mapping.season, mapping.season_year)
		ppc_aliases = _aliases(mapping.ppc_name, ppc.code if ppc else "")
		mill_aliases = _aliases(mapping.mill_name, mill_code)

		tp_keys = set()
		for tp in transit_passes:
			if not _matches(tp.season, season_aliases):
				continue
			if not _matches(tp.ppc, ppc_aliases):
				continue
			if not _matches(tp.miller, mill_aliases) and _normalize(miller_code_part(tp.miller)) != _normalize(
				mill_code
			):
				continue
			tp_keys.add((tp.pass_unique_key or tp.name or "").strip())

		received = 0.0
		rst_numbers = set()
		for key in tp_keys:
			for wbm in wbm_by_pass.get(key, []):
				received += flt(wbm.net_weight)
				rst_no = (wbm.rst_no or "").strip()
				if rst_no:
					rst_numbers.add(rst_no.casefold())

		data.append(
			{
				"season": mapping.season,
				"season_year": mapping.season_year,
				"ppc_display": ppc_display,
				"mill_display": mill_display,
				"season_quantity": flt(mapping.season_quantity),
				"quantity_received": received,
				"rst_count": len(rst_numbers),
				"transit_pass_count": len(tp_keys),
			}
		)

	return data


def _get_wbm_by_pass():
	rows = frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"is_farmer_or_agent": 0},
		fields=["pass_unique_key", "net_weight", "rst_no"],
	)
	by_pass = {}
	for row in rows:
		key = (row.pass_unique_key or "").strip()
		if key:
			by_pass.setdefault(key, []).append(row)
	return by_pass


def _season_aliases(season, year):
	aliases = {season, f"{season} {year}"}
	season_details = frappe.db.get_value("Season Master", season, ["crop_season", "year"], as_dict=True)
	if season_details:
		aliases.update(
			{
				season_details.crop_season,
				season_details.year,
				f"{season_details.crop_season} {season_details.year}",
				f"{season_details.crop_season[:1]}{str(season_details.year)[-2:]}",
			}
		)
	return {_normalize(value) for value in aliases if value}


def _aliases(*values):
	return {_normalize(value) for value in values if value}


def _normalize(value):
	return "".join((value or "").split()).casefold()


def _matches(value, aliases):
	value = (value or "").strip()
	if _normalize(value) in aliases:
		return True
	# Transit pass PPC values are sometimes stored as "PPC Name (Code)".
	if "(" in value and value.endswith(")"):
		name, code = value.rsplit("(", 1)
		return _normalize(name.rstrip()) in aliases or _normalize(code[:-1]) in aliases
	return False
