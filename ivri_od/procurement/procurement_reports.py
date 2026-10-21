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
	("rrc_dc_summary_from_scms", "rrc_dc_summary_from_scms.json"),
	("rrc_transit_pass_from_scms", "rrc_transit_pass_from_scms.json"),
	("gunny_stock_register_details_from_scms", "gunny_stock_register_details_from_scms.json"),
	("lot_search_from_scms", "lot_search_from_scms.json"),
	("paddy_release_from_dcro", "paddy_release_from_dcro.json"),
	("view_dc_from_dcro", "view_dc_from_dcro.json"),
	("dc_transit_challan_from_dcro", "dc_transit_challan_from_dcro.json"),
	("dc_track", "dc_track.json"),
	("tec_report_from_wings", "tec_report_from_wings.json"),
	("stack_status_from_wings", "stack_status_from_wings.json"),
	("booking_delivery_status_from_wings", "booking_delivery_status_from_wings.json"),
	("targets_advanced_paddy_from_wings", "targets_advanced_paddy_from_wings.json"),
	("rejected_lot_for_rrc_from_scms", "rejected_lot_for_rrc_from_scms.json"),
	("pending_lot_in_for_rrc_from_scms", "pending_lot_in_for_rrc_from_scms.json"),
)


def ensure_standard_procurement_reports():
	app_path = frappe.get_app_path("ivri_od")
	for folder, filename in STANDARD_REPORTS:
		path = os.path.join(app_path, "procurement", "report", folder, filename)
		if os.path.isfile(path):
			import_file_by_path(path, force=True, ignore_version=True)
	frappe.clear_cache(doctype="Report")
