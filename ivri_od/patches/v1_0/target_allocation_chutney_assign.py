"""Install Target Allocation & Chhatni Assign; hide Society Master from Procurement desk."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for folder in ("target_allocation", "chhatni_assign"):
		path = os.path.join(
			app_path,
			"procurement",
			"doctype",
			folder,
			f"{folder}.json",
		)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True)

	_hide_society_master_from_procurement_desk()
	_import_procurement_sidebar()
	frappe.clear_cache()


def _hide_society_master_from_procurement_desk():
	if frappe.db.exists("Workspace", "Procurement"):
		frappe.db.delete(
			"Workspace Link",
			{"parent": "Procurement", "link_to": "Society Master"},
		)
		frappe.db.delete(
			"Workspace Shortcut",
			{"parent": "Procurement", "link_to": "Society Master"},
		)

	if frappe.db.exists("Workspace Sidebar", "Procurement"):
		for row in frappe.get_all(
			"Workspace Sidebar Item",
			filters={
				"parent": "Procurement",
				"link_to": "Society Master",
			},
			fields=["name"],
		):
			frappe.delete_doc("Workspace Sidebar Item", row.name, force=1)

	frappe.db.commit()


def _import_procurement_sidebar():
	sidebar_path = os.path.join(
		frappe.get_app_path("ivri_od"),
		"workspace_sidebar",
		"procurement.json",
	)
	if os.path.exists(sidebar_path):
		import_file_by_path(sidebar_path, force=True, ignore_version=True)
