"""Backfill Season Mapping from existing GRN / WBM / Entry pass keys."""

import frappe

from ivri_od.procurement.procurement_sync import sync_all_procurement_season_mappings


def execute():
	frappe.reload_doc("procurement", "doctype", "season_mapping")
	created = sync_all_procurement_season_mappings()
	frappe.logger().info("Season Mapping rows created from procurement backfill: %s", created)
