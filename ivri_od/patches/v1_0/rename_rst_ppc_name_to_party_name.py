"""RST Details: PPC Name field → Party Name."""

from __future__ import annotations

import os

import frappe
from frappe.model.utils.rename_field import rename_field
from frappe.modules.import_file import import_file_by_path


def execute():
	has_ppc = frappe.db.has_column("RST Details", "ppc_name")
	has_party = frappe.db.has_column("RST Details", "party_name")
	if has_ppc and not has_party:
		rename_field("RST Details", "ppc_name", "party_name")
	elif has_ppc and has_party:
		frappe.db.sql(
			"""
			UPDATE `tabRST Details`
			SET party_name = ppc_name
			WHERE (party_name IS NULL OR party_name = '')
			  AND ppc_name IS NOT NULL AND ppc_name != ''
			"""
		)
		frappe.db.sql_ddl("ALTER TABLE `tabRST Details` DROP COLUMN ppc_name")
		frappe.db.commit()

	path = os.path.join(
		frappe.get_app_path("ivri_od"),
		"procurement",
		"doctype",
		"rst_details",
		"rst_details.json",
	)
	if os.path.exists(path):
		import_file_by_path(path, force=True, ignore_version=True)
	frappe.clear_cache(doctype="RST Details")
