"""Restore Procurement Workspace + sidebar after migrate (workspace was missing on site)."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path

from ivri_od.patches.v1_0.setup_ivri_od_desk_app import execute as setup_desk_app


def execute():
	app_path = frappe.get_app_path("ivri_od")

	from ivri_od.procurement.procurement_workspace import apply_procurement_workspace

	apply_procurement_workspace()

	sidebar_path = os.path.join(app_path, "workspace_sidebar", "procurement.json")
	if os.path.exists(sidebar_path):
		import_file_by_path(sidebar_path, force=True, ignore_version=True)

	setup_desk_app()

	for user in frappe.get_all("User", filters={"enabled": 1}, pluck="name"):
		frappe.db.set_value("User", user, "default_app", "ivri_od", update_modified=False)

	frappe.db.set_single_value("System Settings", "default_app", "ivri_od")

	frappe.clear_cache()
	frappe.cache.delete_key("user_perm_can_read")
	frappe.cache.delete_key("bootinfo")
