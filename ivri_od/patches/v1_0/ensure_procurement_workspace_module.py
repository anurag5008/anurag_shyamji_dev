"""Import Procurement workspace from module JSON (prevents orphan deletion on migrate)."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	_import_procurement_workspace_json()
	if not frappe.db.exists("Workspace", "Procurement"):
		from ivri_od.patches.v1_0.restore_procurement_desk import execute as restore_procurement_desk

		restore_procurement_desk()
	frappe.clear_cache()


def _import_procurement_workspace_json():
	path = os.path.join(
		frappe.get_app_path("ivri_od"),
		"procurement",
		"workspace",
		"procurement",
		"procurement.json",
	)
	if os.path.exists(path):
		import_file_by_path(path, force=True, ignore_version=True)
