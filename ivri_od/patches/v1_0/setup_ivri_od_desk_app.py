"""Register ivri_od as a desk app and open Procurement by default."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	_import_desktop_icons()
	_ensure_app_desktop_icon()
	_set_default_app()
	frappe.clear_cache()


def _import_desktop_icons():
	app_path = frappe.get_app_path("ivri_od")
	for filename in ("ivri_od.json", "procurement.json"):
		path = os.path.join(app_path, "ivri_od", "desktop_icon", filename)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True)


def _ensure_app_desktop_icon():
	if not frappe.db.exists("Desktop Icon", "ivri_od"):
		doc = frappe.get_doc(
			{
				"doctype": "Desktop Icon",
				"label": "ivri_od",
				"name": "ivri_od",
				"icon_type": "App",
				"link_type": "External",
				"link": "/desk/procurement",
				"logo_url": "/assets/ivri_od/images/procurement.svg",
				"app": "ivri_od",
				"standard": 1,
				"idx": 1,
				"hidden": 0,
			}
		)
		doc.insert(ignore_permissions=True)

	if frappe.db.exists("Desktop Icon", "Procurement"):
		frappe.db.set_value(
			"Desktop Icon",
			"Procurement",
			{
				"parent_icon": "",
				"idx": 2,
				"hidden": 1,
				"app": "ivri_od",
			},
			update_modified=False,
		)

	_ensure_procurement_workspace_title()


def _set_default_app():
	frappe.db.set_single_value("System Settings", "default_app", "ivri_od")
	frappe.db.set_value("User", "Administrator", "default_app", "ivri_od", update_modified=False)


def _ensure_procurement_workspace_title():
	if not frappe.db.exists("Workspace", "Procurement"):
		return
	if not frappe.db.get_value("Workspace", "Procurement", "title"):
		frappe.db.set_value("Workspace", "Procurement", "title", "Procurement", update_modified=False)
