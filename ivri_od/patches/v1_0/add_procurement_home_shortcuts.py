"""Add procurement records to the standard Home workspace shortcuts."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


HOME_SHORTCUTS = [
	("Gate Entry", "log-in"),
	("Gate Exit", "log-out"),
	("RST Details", "clipboard-list"),
	("Weigh Bridge Measurement", "package"),
	("GRN Note", "file-check"),
]


def execute():
	app_path = frappe.get_app_path("ivri_od")
	sidebar_path = os.path.join(app_path, "workspace_sidebar", "procurement.json")
	if os.path.exists(sidebar_path):
		import_file_by_path(sidebar_path, force=True, ignore_version=True)
	if not frappe.db.exists("Workspace", "Home"):
		return
	idx = frappe.db.sql(
		"SELECT COALESCE(MAX(idx), 0) + 1 FROM `tabWorkspace Shortcut` WHERE parent = 'Home'"
	)[0][0]
	for label, icon in HOME_SHORTCUTS:
		if frappe.db.exists(
			"Workspace Shortcut", {"parent": "Home", "type": "DocType", "link_to": label}
		):
			continue
		frappe.get_doc(
			{
				"doctype": "Workspace Shortcut",
				"parent": "Home",
				"parenttype": "Workspace",
				"parentfield": "shortcuts",
				"idx": idx,
				"type": "DocType",
				"label": label,
				"link_to": label,
				"icon": icon,
			}
		).insert(ignore_permissions=True)
		idx += 1
	frappe.db.commit()
	frappe.clear_cache(doctype="Workspace")
