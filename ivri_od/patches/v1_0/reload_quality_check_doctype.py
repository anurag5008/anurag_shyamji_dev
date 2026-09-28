"""Force-reload Quality Check and Weigh Bridge Measurement DocTypes from app JSON."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for parts in (
		("procurement", "doctype", "quality_check_bag_detail", "quality_check_bag_detail.json"),
		("procurement", "doctype", "quality_check", "quality_check.json"),
		("procurement", "doctype", "gate_entry", "gate_entry.json"),
		("procurement", "doctype", "weigh_bridge_measurement", "weigh_bridge_measurement.json"),
	):
		path = os.path.join(app_path, *parts)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)
	frappe.clear_cache(doctype="Quality Check Bag Detail")
	frappe.clear_cache(doctype="Quality Check")
	frappe.clear_cache(doctype="Weigh Bridge Measurement")
