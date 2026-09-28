"""Install TP Mandi Quantity Fulfillment script report."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	path = os.path.join(
		frappe.get_app_path("ivri_od"),
		"procurement",
		"report",
		"tp_mandi_quantity_fulfillment",
		"tp_mandi_quantity_fulfillment.json",
	)
	if os.path.exists(path):
		import_file_by_path(path, force=True, ignore_version=True)
	frappe.clear_cache()
