"""Mill visit tracking: Gate Out links to Gate In, QC/WBM use open visit."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for parts in (
		("procurement", "doctype", "gate_entry", "gate_entry.json"),
		("procurement", "doctype", "quality_check", "quality_check.json"),
		("procurement", "doctype", "weigh_bridge_measurement", "weigh_bridge_measurement.json"),
	):
		path = os.path.join(app_path, *parts)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)
	frappe.clear_cache(doctype="Gate Entry")
	frappe.clear_cache(doctype="Quality Check")
	frappe.clear_cache(doctype="Weigh Bridge Measurement")
