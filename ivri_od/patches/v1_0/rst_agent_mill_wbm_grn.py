"""Agent on RST/WBM/GRN; mill from transit pass by TP + PPC."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for folder in ("rst_details", "weigh_bridge_measurement", "grn_note"):
		path = os.path.join(
			app_path,
			"procurement",
			"doctype",
			folder,
			f"{folder}.json",
		)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True)
	frappe.clear_cache()
