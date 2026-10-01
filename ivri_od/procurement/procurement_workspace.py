# Copyright (c) 2026, Profezzo and contributors
"""Build Procurement Workspace content (shortcuts + cards) for Frappe desk."""

from __future__ import annotations

import json
import os
import uuid

import frappe
from frappe.modules.import_file import import_file_by_path


FLOW_INTRO = (
	"Typical flow: <b>Masters</b> → <b>Season / targets</b> → <b>PPAS</b> → "
	"<b>Gate</b> → <b>Weigh &amp; QC</b> → <b>Entry / RST / GRN</b>."
)

WORKSPACE_SHORTCUTS = [
	{"label": "Gate Entry", "type": "DocType", "link_to": "Gate Entry", "icon": "log-in", "color": "Blue"},
	{
		"label": "PPAS Transit Pass",
		"type": "DocType",
		"link_to": "PPAS Transit Pass",
		"icon": "file-text",
		"color": "Cyan",
	},
	{
		"label": "Manual PPAS Import",
		"type": "DocType",
		"link_to": "PPAS Transit Pass Import",
		"icon": "clipboard",
		"color": "Teal",
	},
	{
		"label": "Weigh Bridge",
		"type": "DocType",
		"link_to": "Weigh Bridge Measurement",
		"icon": "package",
		"color": "Green",
	},
	{
		"label": "Quality Check",
		"type": "DocType",
		"link_to": "Quality Check",
		"icon": "clipboard-check",
		"color": "Yellow",
	},
	{"label": "RST Details", "type": "DocType", "link_to": "RST Details", "icon": "clipboard-list", "color": "Grey"},
	{"label": "GRN Note", "type": "DocType", "link_to": "GRN Note", "icon": "file-check", "color": "Orange"},
	{
		"label": "Module Overview",
		"type": "Report",
		"link_to": "Procurement Module Overview",
		"icon": "layout-grid",
		"color": "Purple",
	},
]

WORKSPACE_CARDS: list[tuple[str, list[tuple[str, str]]]] = [
	(
		"Masters",
		[
			("Mill Master", "DocType"),
			("PPC Master", "DocType"),
			("District Master", "DocType"),
			("Agent Master", "DocType"),
			("Season Master", "DocType"),
		],
	),
	(
		"Season & targets",
		[
			("Season Mapping", "DocType"),
			("Target Allocation", "DocType"),
			("Chhatni Assign", "DocType"),
			("Daily Planning", "DocType"),
		],
	),
	(
		"PPAS",
		[
			("PPAS Data Extraction", "DocType"),
			("PPAS Transit Pass Import", "DocType"),
			("PPAS Transit Pass", "DocType"),
		],
	),
	(
		"Gate",
		[
			("Gate Entry", "DocType"),
			("Gate Exit", "DocType"),
		],
	),
	(
		"Weigh & quality",
		[
			("Weigh Bridge Measurement", "DocType"),
			("Quality Check", "DocType"),
		],
	),
	(
		"Receipt & GRN",
		[
			("Entry", "DocType"),
			("RST Details", "DocType"),
			("GRN Note", "DocType"),
		],
	),
	(
		"Reports",
		[
			("Procurement Module Overview", "Report"),
			("Season Mapping Receipt Summary", "Report"),
			("Mill PPC Season Quantity Summary", "Report"),
			("TP Mandi Quantity Fulfillment", "Report"),
			("Vehicle Gate Movement Summary", "Report"),
		],
	),
]

QUERY_REPORTS = {
	"Procurement Module Overview",
	"Season Mapping Receipt Summary",
	"Mill PPC Season Quantity Summary",
	"TP Mandi Quantity Fulfillment",
	"Vehicle Gate Movement Summary",
}


def _block_id() -> str:
	return uuid.uuid4().hex[:10]


def build_workspace_content() -> str:
	blocks: list[dict] = [
		{
			"id": _block_id(),
			"type": "header",
			"data": {"text": '<span class="h4"><b>Procurement desk</b></span>', "col": 12},
		},
		{"id": _block_id(), "type": "paragraph", "data": {"text": FLOW_INTRO, "col": 12}},
		{
			"id": _block_id(),
			"type": "header",
			"data": {"text": '<span class="h4"><b>Quick shortcuts</b></span>', "col": 12},
		},
	]
	for row in WORKSPACE_SHORTCUTS:
		blocks.append(
			{
				"id": _block_id(),
				"type": "shortcut",
				"data": {"shortcut_name": row["label"], "col": 3},
			}
		)
	blocks.append({"id": _block_id(), "type": "spacer", "data": {"col": 12}})
	blocks.append(
		{
			"id": _block_id(),
			"type": "header",
			"data": {"text": '<span class="h4"><b>All modules</b></span>', "col": 12},
		}
	)
	for card_name, _items in WORKSPACE_CARDS:
		blocks.append(
			{"id": _block_id(), "type": "card", "data": {"card_name": card_name, "col": 4}}
		)
	return json.dumps(blocks)


def ensure_procurement_workspace_after_migrate():
	"""Rebuild Procurement workspace from code (shortcuts + PPAS links stay in sync)."""
	apply_procurement_workspace()
	sidebar_path = os.path.join(frappe.get_app_path("ivri_od"), "workspace_sidebar", "procurement.json")
	if os.path.exists(sidebar_path):
		import_file_by_path(sidebar_path, force=True, ignore_version=True)
	frappe.clear_cache()


def apply_procurement_workspace():
	"""Create or update public Procurement workspace with shortcuts visible on desk."""
	if not frappe.db.exists("Workspace", "Procurement"):
		doc = frappe.new_doc("Workspace")
		doc.name = "Procurement"
		doc.title = "Procurement"
		doc.label = "Procurement"
		doc.module = "Procurement"
		doc.app = "ivri_od"
		doc.public = 1
		doc.is_hidden = 0
		doc.icon = "building-2"
		doc.type = "Workspace"
	else:
		doc = frappe.get_doc("Workspace", "Procurement")

	if not doc.type:
		doc.type = "Workspace"

	doc.content = build_workspace_content()

	doc.shortcuts = []
	for row in WORKSPACE_SHORTCUTS:
		child = doc.append("shortcuts", {})
		child.label = row["label"]
		child.type = row["type"]
		child.link_to = row["link_to"]
		child.icon = row.get("icon") or ""
		child.color = row.get("color") or "Grey"
		child.doc_view = "List"
		if row["type"] == "Report" and row["link_to"] in QUERY_REPORTS:
			child.report_ref_doctype = frappe.db.get_value("Report", row["link_to"], "ref_doctype")

	doc.links = []
	for card_name, items in WORKSPACE_CARDS:
		doc.append(
			"links",
			{
				"type": "Card Break",
				"label": card_name,
				"link_count": len(items),
				"hidden": 0,
				"is_query_report": 0,
				"onboard": 0,
			},
		)
		for link_to, link_type in items:
			is_report = link_type == "Report"
			doc.append(
				"links",
				{
					"type": "Link",
					"label": _link_label(link_to, link_type),
					"link_type": link_type,
					"link_to": link_to,
					"hidden": 0,
					"is_query_report": 1 if is_report and link_to in QUERY_REPORTS else 0,
					"onboard": 0,
				},
			)

	doc.flags.ignore_permissions = True
	doc.save(ignore_version=True)
	frappe.db.commit()


def _link_label(link_to: str, link_type: str) -> str:
	if link_type != "Report":
		return link_to
	return {
		"Procurement Module Overview": "Module Overview",
		"Season Mapping Receipt Summary": "Season Mapping Receipt",
		"Mill PPC Season Quantity Summary": "Mill PPC Season Qty",
		"TP Mandi Quantity Fulfillment": "TP Mandi Fulfillment",
		"Vehicle Gate Movement Summary": "Vehicle Gate Movement",
	}.get(link_to, link_to)
