"""Reload weighment doctypes after QT weight field label rename."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for parts in (
		("procurement", "doctype", "weigh_bridge_measurement", "weigh_bridge_measurement.json"),
		("procurement", "doctype", "grn_note", "grn_note.json"),
	):
		path = os.path.join(app_path, *parts)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)
	frappe.clear_cache(doctype="Weigh Bridge Measurement")
	frappe.clear_cache(doctype="GRN Note")
