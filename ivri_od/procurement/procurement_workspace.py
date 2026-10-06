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
			("Abstract Report", "Report"),
			("Abstract Physical", "Report"),
			("TP Mandi Quantity Fulfillment", "Report"),
			("Mandi Book", "Report"),
			("Vehicle Gate Movement Summary", "Report"),
		],
	),
]

# Hidden from Procurement desk (doctype remains available via search / links).
HIDDEN_WORKSPACE_LINKS: tuple[tuple[str, str], ...] = (
	("Season Mapping", "DocType"),
	("Season Mapping Receipt Summary", "Report"),
	("Chhatni Tracking", "Report"),
	("Pass RST WBM Summary", "Report"),
)

PASS_RST_REPORT = "Pass RST WBM Summary"
PASS_RST_SIDEBAR_LABEL = "Pass RST & WBM"
PASS_RST_QUERY_URL = "/app/query-report/Pass%20RST%20WBM%20Summary"

QUERY_REPORTS = {
	"Procurement Module Overview",
	"Season Mapping Receipt Summary",
	"Abstract Report",
	"Abstract Physical",
	"TP Mandi Quantity Fulfillment",
	"Mandi Book",
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
	sync_procurement_desk_ui()


def sync_procurement_desk_ui():
	"""Install reports, rebuild workspace, sidebar, and clear desk cache (callable from patches)."""
	from ivri_od.procurement.procurement_reports import ensure_standard_procurement_reports

	ensure_standard_procurement_reports()
	apply_procurement_workspace()
	_import_procurement_sidebar()
	_cleanup_hidden_workspace_links()
	frappe.clear_cache()
	_clear_procurement_desk_cache()


def _import_procurement_sidebar():
	sidebar_path = os.path.join(frappe.get_app_path("ivri_od"), "workspace_sidebar", "procurement.json")
	if os.path.exists(sidebar_path):
		import_file_by_path(sidebar_path, force=True, ignore_version=True)


def _cleanup_hidden_workspace_links():
	if not frappe.db.exists("Workspace", "Procurement"):
		return
	for link_to, link_type in HIDDEN_WORKSPACE_LINKS:
		frappe.db.delete(
			"Workspace Link",
			{"parent": "Procurement", "link_to": link_to, "link_type": link_type},
		)
		shortcut_type = "Report" if link_type == "Report" else "DocType"
		frappe.db.delete(
			"Workspace Shortcut",
			{"parent": "Procurement", "link_to": link_to, "type": shortcut_type},
		)
	if frappe.db.exists("Workspace Sidebar", "Procurement"):
		frappe.db.sql(
			"""
			DELETE FROM `tabWorkspace Sidebar Item`
			WHERE parent = 'Procurement'
				AND (
					(link_to = 'Season Mapping' AND link_type = 'DocType')
					OR link_to IN (
						'Season Mapping Receipt Summary',
						'Chhatni Tracking',
						'Pass RST WBM Summary'
					)
					OR label IN (
						'Season Mapping',
						'Season Mapping Receipt',
						'Chhatni Tracking',
						'Pass RST & WBM'
					)
					OR url LIKE %s
					OR url LIKE %s
					OR url LIKE %s
				)
			""",
			(
				"%Season%20Mapping%20Receipt%",
				"%Chhatni%20Tracking%",
				"%Pass%20RST%20WBM%20Summary%",
			),
		)
	frappe.db.commit()


def _clear_procurement_desk_cache():
	frappe.cache.delete_key("bootinfo")
	frappe.cache.delete_key("user_perm_can_read")


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
		if not _workspace_target_exists(row["link_to"], row["type"]):
			continue
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
		valid_items = [
			(link_to, link_type)
			for link_to, link_type in items
			if _workspace_target_exists(link_to, link_type)
		]
		if not valid_items:
			continue
		doc.append(
			"links",
			{
				"type": "Card Break",
				"label": card_name,
				"link_count": len(valid_items),
				"hidden": 0,
				"is_query_report": 0,
				"onboard": 0,
			},
		)
		for link_to, link_type in valid_items:
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
	doc.flags.ignore_links = True
	doc.save(ignore_version=True)
	frappe.db.commit()


def _workspace_target_exists(link_to: str, link_type: str) -> bool:
	link_to = (link_to or "").strip()
	if not link_to:
		return False
	if link_type == "DocType":
		return bool(frappe.db.exists("DocType", link_to))
	if link_type == "Report":
		return bool(frappe.db.exists("Report", link_to))
	return True


def _link_label(link_to: str, link_type: str) -> str:
	if link_type != "Report":
		return link_to
	return {
		"Procurement Module Overview": "Module Overview",
		"Season Mapping Receipt Summary": "Season Mapping Receipt",
		"Abstract Report": "Abstract Report",
		"Abstract Physical": "Abstract Physical",
		"TP Mandi Quantity Fulfillment": "TP Mandi Fulfillment",
		"Mandi Book": "Mandi Book",
		"Vehicle Gate Movement Summary": "Vehicle Gate Movement",
	}.get(link_to, link_to)
