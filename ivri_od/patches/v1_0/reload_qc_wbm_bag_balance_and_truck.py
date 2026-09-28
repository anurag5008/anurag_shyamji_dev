"""Reload QC/WBM doctypes, allow multiple docs per TP, invert truck checkbox meaning."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	if frappe.db.table_exists("Weigh Bridge Measurement"):
		frappe.db.sql(
			"""
			UPDATE `tabWeigh Bridge Measurement`
			SET same_truck_as_transit_pass = 1 - IFNULL(same_truck_as_transit_pass, 0)
			"""
		)

	app_path = frappe.get_app_path("ivri_od")
	for parts in (
		("procurement", "doctype", "quality_check", "quality_check.json"),
		("procurement", "doctype", "weigh_bridge_measurement", "weigh_bridge_measurement.json"),
	):
		path = os.path.join(app_path, *parts)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)

	frappe.clear_cache(doctype="Quality Check")
	frappe.clear_cache(doctype="Weigh Bridge Measurement")
