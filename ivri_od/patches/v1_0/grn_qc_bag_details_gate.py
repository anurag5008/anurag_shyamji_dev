"""GRN Note: QC bag child table, Gate Entry in QC Details, remove attachment."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	path = os.path.join(
		frappe.get_app_path("ivri_od"),
		"procurement",
		"doctype",
		"grn_note",
		"grn_note.json",
	)
	if os.path.exists(path):
		import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)
	frappe.clear_cache(doctype="GRN Note")
