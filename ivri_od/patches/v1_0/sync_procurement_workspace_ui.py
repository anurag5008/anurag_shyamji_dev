"""Force-sync Procurement workspace home shortcuts and sidebar links from app JSON."""

from __future__ import annotations

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path


PROCUREMENT_DOCTYPES = [
	("Mill Master", "factory"),
	("PPC Master", "map-pin"),
	("Season Master", "calendar"),
	("Daily Planning", "truck"),
	("PPAS Data Extraction", "download"),
	("PPAS Transit Pass", "file-text"),
	("Gate Entry", "log-in"),
	("Gate Exit", "log-out"),
	("Weigh Bridge Measurement", "package"),
	("Quality Check", "clipboard-check"),
	("Entry", "receipt"),
	("GRN Note", "file-check"),
	("RST Details", "clipboard-list"),
]


def execute():
	_ensure_procurement_workspace_title()
	from ivri_od.procurement.procurement_workspace import sync_procurement_desk_ui

	sync_procurement_desk_ui()


def _ensure_procurement_workspace_title():
	if not frappe.db.exists("Workspace", "Procurement"):
		return
	if not frappe.db.get_value("Workspace", "Procurement", "title"):
		frappe.db.set_value("Workspace", "Procurement", "title", "Procurement", update_modified=False)


def _procurement_workspace_json_path() -> str:
	app_path = frappe.get_app_path("ivri_od")
	return os.path.join(
		app_path,
		"procurement",
		"workspace",
		"procurement",
		"procurement.json",
	)


def _rebuild_procurement_workspace_from_json():
	if not frappe.db.exists("Workspace", "Procurement"):
		return

	path = _procurement_workspace_json_path()
	if not os.path.exists(path):
		return

	with open(path, encoding="utf-8") as handle:
		data = json.load(handle)

	content = data.get("content")
	if content:
		frappe.db.set_value("Workspace", "Procurement", "content", content, update_modified=True)

	frappe.db.delete("Workspace Shortcut", {"parent": "Procurement"})
	for idx, row in enumerate(data.get("shortcuts") or [], start=1):
		frappe.get_doc(
			{
				"doctype": "Workspace Shortcut",
				"parent": "Procurement",
				"parenttype": "Workspace",
				"parentfield": "shortcuts",
				"idx": idx,
				**row,
			}
		).insert(ignore_permissions=True)

	frappe.db.delete("Workspace Link", {"parent": "Procurement"})
	for idx, row in enumerate(data.get("links") or [], start=1):
		frappe.get_doc(
			{
				"doctype": "Workspace Link",
				"parent": "Procurement",
				"parenttype": "Workspace",
				"parentfield": "links",
				"idx": idx,
				**row,
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()

	shortcut_count = frappe.db.count("Workspace Shortcut", {"parent": "Procurement"})
	expected = len(data.get("shortcuts") or [])
	if expected and shortcut_count != expected:
		frappe.throw(
			f"Procurement workspace sync failed: expected {expected} shortcuts, found {shortcut_count}."
		)


def _force_import_sidebar_only():
	app_path = frappe.get_app_path("ivri_od")
	sidebar_path = os.path.join(app_path, "workspace_sidebar", "procurement.json")
	if os.path.exists(sidebar_path):
		import_file_by_path(sidebar_path, force=True, ignore_version=True)


def _force_import_procurement_workspace():
	workspace_path = _procurement_workspace_json_path()
	if os.path.exists(workspace_path):
		import_file_by_path(workspace_path, force=True, ignore_version=True, reset_permissions=True)

	app_path = frappe.get_app_path("ivri_od")
	sidebar_path = os.path.join(app_path, "workspace_sidebar", "procurement.json")
	if os.path.exists(sidebar_path):
		import_file_by_path(sidebar_path, force=True, ignore_version=True)


def _rebuild_procurement_sidebar():
	if not frappe.db.exists("Workspace Sidebar", "Procurement"):
		return

	doc = frappe.get_doc("Workspace Sidebar", "Procurement")
	doc.items = []

	doc.append(
		"items",
		{
			"label": "Home",
			"link_to": "Procurement",
			"link_type": "Workspace",
			"type": "Link",
			"icon": "home",
			"idx": 1,
		},
	)

	idx = 2
	for label, icon in PROCUREMENT_DOCTYPES:
		doc.append(
			"items",
			{
				"label": label,
				"link_to": label,
				"link_type": "DocType",
				"type": "Link",
				"icon": icon,
				"idx": idx,
			},
		)
		idx += 1

	doc.save(ignore_permissions=True)
