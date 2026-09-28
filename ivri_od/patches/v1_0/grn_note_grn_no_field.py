"""Add GRN No field and backfill from document name."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	path = os.path.join(app_path, "procurement", "doctype", "grn_note", "grn_note.json")
	if os.path.exists(path):
		import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)

	if not frappe.db.has_column("GRN Note", "grn_no"):
		return

	for name in frappe.get_all("GRN Note", pluck="name"):
		if not (frappe.db.get_value("GRN Note", name, "grn_no") or "").strip():
			frappe.db.set_value("GRN Note", name, "grn_no", name, update_modified=False)

	frappe.db.commit()
	frappe.clear_cache(doctype="GRN Note")
