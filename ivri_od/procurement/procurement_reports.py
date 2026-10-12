# Copyright (c) 2026, Profezzo and contributors
"""Install standard Procurement script reports from app fixtures."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path

# (folder under procurement/report, json filename)
STANDARD_REPORTS: tuple[tuple[str, str], ...] = (
	("pass_rst_wbm_summary", "pass_rst_wbm_summary.json"),
	("tp_mandi_quantity_fulfillment", "tp_mandi_quantity_fulfillment.json"),
	("chhatni_tracking", "chhatni_tracking.json"),
	("mandi_book", "mandi_book.json"),
	("vehicle_gate_movement_summary", "vehicle_gate_movement_summary.json"),
	("procurement_module_overview", "procurement_module_overview.json"),
	("season_mapping_receipt_summary", "season_mapping_receipt_summary.json"),
	("abstract_report", "abstract_report.json"),
	("abstract_physical", "abstract_physical.json"),
	("mill_ppc_season_quantity_summary", "mill_ppc_season_quantity_summary.json"),
	("entry_report", "entry_report.json"),
)


def ensure_standard_procurement_reports():
	app_path = frappe.get_app_path("ivri_od")
	for folder, filename in STANDARD_REPORTS:
		path = os.path.join(app_path, "procurement", "report", folder, filename)
		if os.path.isfile(path):
			import_file_by_path(path, force=True, ignore_version=True)
	frappe.clear_cache(doctype="Report")
