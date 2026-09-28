"""Reload Quality Check and Weigh Bridge Measurement after farmer/agent field updates."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for doctype in ("quality_check", "weigh_bridge_measurement"):
		path = os.path.join(
			app_path,
			"procurement",
			"doctype",
			doctype,
			f"{doctype}.json",
		)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)
	for doctype in ("Quality Check", "Weigh Bridge Measurement"):
		frappe.clear_cache(doctype=doctype)
