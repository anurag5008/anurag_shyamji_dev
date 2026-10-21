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

# Rice handover: one page lists every report built from SCMS portal data.
RRC_WORKSPACE = "RRC Detail from SCMS"
RRC_WORKSPACE_SLUG = "rrc-detail-from-scms"
# Custom HTML Block on each portal report page: "Manual Entry" button with a
# drop-down of that page's forms in procurement/portal_manual.py (group "rrc" or
# "dcro"; code in public/js/portal_detail_table.bundle.js).
RRC_MANUAL_BLOCK = "RRC Manual Entry"
MANUAL_BLOCK_HTML = """<div class="manual-entry">
	<div class="manual-entry-dropdown">
		<button class="btn btn-primary btn-sm manual-entry-button">Manual Entry &#9662;</button>
		<div class="dropdown-menu manual-entry-menu"></div>
	</div>
	<span class="text-muted small">Enter {portal} rows by hand when they cannot be read from the portal.
	Rows read from the portal always replace them.</span>
</div>"""
MANUAL_BLOCK_STYLE = """.manual-entry { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.manual-entry-dropdown { position: relative; }
.manual-entry-menu { display: none; position: absolute; top: 100%; left: 0; z-index: 1000; min-width: 260px; }"""
MANUAL_BLOCK_SCRIPT = 'ivri_od.portal.setup_manual_entry_block(root_element, "{group}");'
RRC_REPORTS: list[tuple[str, str, str]] = [
	# (report, icon, colour)
	("RRC DC Summary from SCMS", "truck", "Blue"),
	("RRC Transit Pass from SCMS", "file-text", "Cyan"),
	("Gunny Stock Register Details from SCMS", "package", "Green"),
	("Lot Search from SCMS", "search", "Purple"),
	("Rejected Lot for RRC from SCMS", "x-circle", "Red"),
	("Pending Lot In for RRC from SCMS", "clock", "Orange"),
]

# Paddy release: one page lists every report built from DCRO portal data.
DCRO_WORKSPACE = "DCRO Details"
DCRO_WORKSPACE_SLUG = "dcro-details"
DCRO_MANUAL_BLOCK = "DCRO Manual Entry"
DCRO_REPORTS: list[tuple[str, str, str]] = [
	("Paddy Release from DCRO", "truck", "Green"),
	("View DC from DCRO", "file-text", "Blue"),
	("DC Transit Challan from DCRO", "file-check", "Orange"),
]

# One line per DC: lots to deliver (View DC) against lots delivered (DC Transit Challan,
# SCMS Lot Search). Built from DCRO and SCMS together, so it sits on the Procurement page.
DC_TRACK_REPORT = "DC Track"

# FCI depot data: one page lists every report built from WINGS (fciarms.in) portal data.
WINGS_WORKSPACE = "WINGS Details"
WINGS_WORKSPACE_SLUG = "wings-details"
WINGS_MANUAL_BLOCK = "WINGS Manual Entry"
WINGS_REPORTS: list[tuple[str, str, str]] = [
	("TEC Report from WINGS", "file-check", "Blue"),
	("Stack Status from WINGS", "layers", "Purple"),
	("Booking Delivery Status from WINGS", "truck", "Green"),
	("Targets Advanced Paddy from WINGS", "target", "Orange"),
]

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
	{"label": DC_TRACK_REPORT, "type": "Report", "link_to": DC_TRACK_REPORT, "icon": "check-square", "color": "Purple"},
	{
		"label": "Module Overview",
		"type": "Report",
		"link_to": "Procurement Module Overview",
		"icon": "layout-grid",
		"color": "Purple",
	},
]

# Box "Government Portals Reports" among the module cards of the Procurement page:
# a link to each portal's page of reports. A Custom HTML Block drawn like the other
# cards, because a card's links can only open a DocType, Page or Report, not a workspace.
PORTAL_SHORTCUTS = [
	{
		"label": DCRO_WORKSPACE,
		"type": "URL",
		"url": "/app/" + DCRO_WORKSPACE_SLUG,
		"link_to": "",
		"icon": "truck",
		"color": "Green",
	},
	{
		"label": WINGS_WORKSPACE,
		"type": "URL",
		"url": "/app/" + WINGS_WORKSPACE_SLUG,
		"link_to": "",
		"icon": "layers",
		"color": "Blue",
	},
	{
		"label": RRC_WORKSPACE,
		"type": "URL",
		"url": "/app/" + RRC_WORKSPACE_SLUG,
		"link_to": "",
		"icon": "file-text",
		"color": "Cyan",
	},
]
PORTAL_SECTION = "Government Portals Reports"
PORTAL_CARD_STYLE = """.portal-card { margin: -7px; padding: 10px 12px; border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg); background: var(--card-bg); height: calc(100% + 14px); box-sizing: border-box; }
.portal-card-title { font-size: var(--text-base); font-weight: 600; color: var(--heading-color, var(--text-color)); }
.portal-link { display: block; text-decoration: none; font-size: var(--text-sm); color: var(--text-color);
	padding: 4px; margin-left: -4px; border-radius: var(--border-radius-md); }
.portal-link:first-of-type { margin-top: 12px; }
.portal-link:hover { color: var(--invert-neutral); }"""
PORTAL_CARD_SCRIPT = """root_element.querySelectorAll("a[data-route]").forEach((a) =>
	a.addEventListener("click", (e) => {
		e.preventDefault();
		frappe.set_route(a.dataset.route);
	})
);"""

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
		"Govt portals",
		[
			("Portal Data Extraction", "DocType"),
			("Portal Record", "DocType"),
			("Portal Site", "DocType"),
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
			("Entry Report", "Report"),
			(DC_TRACK_REPORT, "Report"),
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
	"Entry Report",
	DC_TRACK_REPORT,
	*(name for name, _icon, _color in RRC_REPORTS),
	*(name for name, _icon, _color in DCRO_REPORTS),
	*(name for name, _icon, _color in WINGS_REPORTS),
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
		if card_name == "Govt portals":
			blocks.append(
				{"id": _block_id(), "type": "custom_block", "data": {"custom_block_name": PORTAL_SECTION, "col": 4}}
			)
	return json.dumps(blocks)


def _ensure_portal_card_block():
	"""The "Government Portals Reports" box: links to DCRO Details, WINGS Details, RRC Detail from SCMS."""
	links = "".join(
		f'<a class="portal-link" href="{row["url"]}" data-route="{row["url"].rsplit("/", 1)[-1]}">{row["label"]}</a>'
		for row in PORTAL_SHORTCUTS
	)
	html = f'<div class="portal-card"><div class="portal-card-title">{PORTAL_SECTION}</div>{links}</div>'
	if frappe.db.exists("Custom HTML Block", PORTAL_SECTION):
		doc = frappe.get_doc("Custom HTML Block", PORTAL_SECTION)
	else:
		doc = frappe.new_doc("Custom HTML Block")
	doc.update({"html": html, "style": PORTAL_CARD_STYLE, "script": PORTAL_CARD_SCRIPT, "private": 0})
	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert(set_name=PORTAL_SECTION)
	else:
		doc.save()


def ensure_procurement_workspace_after_migrate():
	"""Rebuild Procurement workspace from code (shortcuts + PPAS links stay in sync)."""
	sync_procurement_desk_ui()


def sync_procurement_desk_ui():
	"""Install reports, rebuild workspace, sidebar, and clear desk cache (callable from patches)."""
	from ivri_od.procurement.procurement_reports import ensure_standard_procurement_reports

	ensure_standard_procurement_reports()
	apply_procurement_workspace()
	apply_rrc_workspace()
	apply_dcro_workspace()
	apply_wings_workspace()
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

	_ensure_portal_card_block()
	doc.content = build_workspace_content()
	doc.custom_blocks = []
	doc.append("custom_blocks", {"custom_block_name": PORTAL_SECTION, "label": PORTAL_SECTION})

	doc.shortcuts = []
	for row in WORKSPACE_SHORTCUTS:
		if row["type"] != "URL" and not _workspace_target_exists(row["link_to"], row["type"]):
			continue
		child = doc.append("shortcuts", {})
		child.label = row["label"]
		child.type = row["type"]
		child.link_to = row["link_to"]
		child.url = row.get("url") or ""
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


def apply_rrc_workspace():
	"""Page "RRC Detail from SCMS": a shortcut and a link for each SCMS report."""
	_apply_portal_workspace(
		RRC_WORKSPACE,
		"file-text",
		"Rice handover data read from the SCMS portal with <b>Portal Data Extraction</b>.",
		RRC_REPORTS,
		"SCMS reports",
		RRC_MANUAL_BLOCK,
		"rrc",
		"SCMS",
	)


def apply_dcro_workspace():
	"""Page "DCRO Details": a shortcut and a link for each DCRO report (paddy release)."""
	_apply_portal_workspace(
		DCRO_WORKSPACE,
		"truck",
		"Paddy release data read from the DCRO portal with <b>Portal Data Extraction</b>.",
		DCRO_REPORTS,
		"DCRO reports",
		DCRO_MANUAL_BLOCK,
		"dcro",
		"DCRO",
	)


def apply_wings_workspace():
	"""Page "WINGS Details": a shortcut and a link for each WINGS report (TEC, stack status)."""
	_apply_portal_workspace(
		WINGS_WORKSPACE,
		"layers",
		"TEC, stack, booking/delivery and target data read from the WINGS portal (fciarms.in) with <b>Portal Data Extraction</b>.",
		WINGS_REPORTS,
		"WINGS reports",
		WINGS_MANUAL_BLOCK,
		"wings",
		"WINGS",
	)


def _apply_portal_workspace(title, icon, intro, report_list, card, block, group, portal):
	"""A page of portal reports with a Manual Entry button (none when ``block`` is
	None). A child page of Procurement (not an app of its own), opened from its
	Procurement shortcut. Not "hidden": Frappe shows hidden pages only to Workspace Managers."""
	reports = [r for r in report_list if frappe.db.exists("Report", r[0])]
	if block:
		_ensure_manual_entry_block(block, group, portal)
	if frappe.db.exists("Workspace", title):
		doc = frappe.get_doc("Workspace", title)
	else:
		doc = frappe.new_doc("Workspace")
		doc.name = doc.title = doc.label = title
	doc.update(
		{
			"module": "Procurement",
			"app": "ivri_od",
			"public": 1,
			"is_hidden": 0,
			"icon": icon,
			"type": "Workspace",
			"parent_page": "Procurement",
		}
	)
	blocks = [
		{
			"id": _block_id(),
			"type": "header",
			"data": {"text": f'<span class="h4"><b>{title}</b></span>', "col": 12},
		},
		{"id": _block_id(), "type": "paragraph", "data": {"text": intro, "col": 12}},
	]
	doc.shortcuts = []
	doc.links = []
	doc.custom_blocks = []
	if block:
		blocks.append({"id": _block_id(), "type": "custom_block", "data": {"custom_block_name": block, "col": 12}})
		doc.append("custom_blocks", {"custom_block_name": block, "label": block})
	doc.append("links", {"type": "Card Break", "label": card, "link_count": len(reports)})
	for name, report_icon, color in reports:
		doc.append(
			"shortcuts",
			{
				"label": name,
				"type": "Report",
				"link_to": name,
				"icon": report_icon,
				"color": color,
				"report_ref_doctype": "Portal Record",
			},
		)
		doc.append(
			"links",
			{"type": "Link", "label": name, "link_type": "Report", "link_to": name, "is_query_report": 1},
		)
		blocks.append({"id": _block_id(), "type": "shortcut", "data": {"shortcut_name": name, "col": 4}})
	blocks.append({"id": _block_id(), "type": "card", "data": {"card_name": card, "col": 4}})
	doc.content = json.dumps(blocks)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_links = True
	doc.save(ignore_version=True)
	frappe.db.commit()


def _ensure_manual_entry_block(name, group, portal):
	"""Public block (no roles): the server checks who may save manual rows."""
	if frappe.db.exists("Custom HTML Block", name):
		doc = frappe.get_doc("Custom HTML Block", name)
	else:
		doc = frappe.new_doc("Custom HTML Block")
	doc.update(
		{
			"html": MANUAL_BLOCK_HTML.format(portal=portal),
			"style": MANUAL_BLOCK_STYLE,
			"script": MANUAL_BLOCK_SCRIPT.format(group=group),
			"private": 0,
		}
	)
	doc.flags.ignore_permissions = True
	if doc.is_new():
		doc.insert(set_name=name)
	else:
		doc.save()


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
		"Entry Report": "Entry Report",
	}.get(link_to, link_to)
