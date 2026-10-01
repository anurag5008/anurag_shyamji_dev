# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import frappe
from frappe import _


MODULE_CATALOG = [
	{
		"area": "Reference Data",
		"component_type": "DocType",
		"name": "Mill Master",
		"description": "Rice mill master with mill codes used across procurement.",
	},
	{
		"area": "Reference Data",
		"component_type": "DocType",
		"name": "Mill Code Detail",
		"description": "Child table for mill code lines on Mill Master.",
	},
	{
		"area": "Reference Data",
		"component_type": "DocType",
		"name": "PPC Master",
		"description": "Procurement centre (PPC) with district and agent links.",
	},
	{
		"area": "Reference Data",
		"component_type": "DocType",
		"name": "District Master",
		"description": "District names used on PPC Master.",
	},
	{
		"area": "Reference Data",
		"component_type": "DocType",
		"name": "Agent Master",
		"description": "Agent names used on PPC Master.",
	},
	{
		"area": "Reference Data",
		"component_type": "DocType",
		"name": "Society Master",
		"description": "Farmer society / PACS (used in planning & GRN; hidden from Procurement sidebar).",
	},
	{
		"area": "Reference Data",
		"component_type": "DocType",
		"name": "Season Master",
		"description": "Kharif / Rabi seasons by year for planning and mapping.",
	},
	{
		"area": "Season & Planning",
		"component_type": "DocType",
		"name": "Season Mapping",
		"description": "Mill + PPC season quantity allocation and GRN progress.",
	},
	{
		"area": "Season & Planning",
		"component_type": "DocType",
		"name": "Target Allocation",
		"description": "PPC target quantity by agent and mill.",
	},
	{
		"area": "Season & Planning",
		"component_type": "DocType",
		"name": "Chhatni Assign",
		"description": "Chutney kg per quintal and auto percentage by PPC, season, and mill.",
	},
	{
		"area": "Season & Planning",
		"component_type": "DocType",
		"name": "Daily Planning",
		"description": "Daily truck / procurement plan by PPC and season.",
	},
	{
		"area": "PPAS Integration",
		"component_type": "DocType",
		"name": "PPAS Data Extraction",
		"description": "Load PPAS portal session, extract transit pass Excel, import to ERP.",
	},
	{
		"area": "PPAS Integration",
		"component_type": "DocType",
		"name": "PPAS Transit Pass",
		"description": "Transit passes imported from PPAS (unique per season + PPC + TP no.).",
	},
	{
		"area": "PPAS Integration",
		"component_type": "Integration",
		"name": "PPAS Agent (Windows)",
		"description": "Local agent on port 8765 — Chrome login, scrape, Excel download.",
	},
	{
		"area": "Gate Operations",
		"component_type": "DocType",
		"name": "Gate Entry",
		"description": "Vehicle gate-in with driver and transit pass linkage.",
	},
	{
		"area": "Gate Operations",
		"component_type": "DocType",
		"name": "Gate Exit",
		"description": "Vehicle gate-out linked to gate entry.",
	},
	{
		"area": "Weighing & Quality",
		"component_type": "DocType",
		"name": "Weigh Bridge Measurement",
		"description": "Load / tare / net weight with bag breakdown.",
	},
	{
		"area": "Weighing & Quality",
		"component_type": "DocType",
		"name": "Quality Check",
		"description": "Paddy QC decision and bag types received.",
	},
	{
		"area": "Receipt & GRN",
		"component_type": "DocType",
		"name": "Entry",
		"description": "Quantity entry against transit pass unique key.",
	},
	{
		"area": "Receipt & GRN",
		"component_type": "DocType",
		"name": "RST Details",
		"description": "RST reference lines for receipt documentation.",
	},
	{
		"area": "Receipt & GRN",
		"component_type": "DocType",
		"name": "GRN Note",
		"description": "Goods receipt note with paddy procured from QC / WBM.",
	},
	{
		"area": "Receipt & GRN",
		"component_type": "DocType",
		"name": "GRN Entry Detail",
		"description": "Line-level GRN entry detail.",
	},
	{
		"area": "Analytics",
		"component_type": "Report",
		"name": "Procurement Module Overview",
		"description": "This catalog — what is built in the IVRI Procurement module.",
	},
	{
		"area": "Analytics",
		"component_type": "Report",
		"name": "Season Mapping Receipt Summary",
		"description": "Season mapping quantity vs GRN / transit pass receipt.",
	},
	{
		"area": "Analytics",
		"component_type": "Report",
		"name": "Mill PPC Season Quantity Summary",
		"description": "Assigned vs received quantity by mill, PPC, and season.",
	},
	{
		"area": "Analytics",
		"component_type": "Report",
		"name": "TP Mandi Quantity Fulfillment",
		"description": "Transit pass quantity vs mandi allocation.",
	},
	{
		"area": "Analytics",
		"component_type": "Report",
		"name": "Vehicle Gate Movement Summary",
		"description": "Gate-in to gate-out movement timeline.",
	},
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{
			"label": _("Area"),
			"fieldname": "area",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Type"),
			"fieldname": "component_type",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Name"),
			"fieldname": "name",
			"fieldtype": "Data",
			"width": 280,
		},
		{
			"label": _("Records"),
			"fieldname": "record_count",
			"fieldtype": "Int",
			"width": 100,
		},
	]


def _record_count(component_type, name):
	if component_type == "DocType" and frappe.db.table_exists(name):
		return frappe.db.count(name)
	return None


def _open_link(component_type, name):
	if component_type == "DocType":
		return f"/app/{frappe.scrub(name)}"
	if component_type == "Report":
		from urllib.parse import quote

		return f"/app/query-report/{quote(name)}"
	return ""


def get_data(filters):
	rows = []
	for item in MODULE_CATALOG:
		if filters.get("area") and item["area"] != filters.area:
			continue

		count = _record_count(item["component_type"], item["name"])
		rows.append(
			{
				"area": item["area"],
				"component_type": item["component_type"],
				"name": item["name"],
				"record_count": count if count is not None else "",
				"description": item["description"],
				"open_link": _open_link(item["component_type"], item["name"]),
			}
		)

	return rows
