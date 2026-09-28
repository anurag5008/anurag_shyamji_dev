"""GRN Note: Entry Data child table from Entry docs by pass unique key."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for doctype in ("grn_entry_detail", "grn_note"):
		path = os.path.join(
			app_path,
			"procurement",
			"doctype",
			doctype,
			f"{doctype}.json",
		)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True, reset_permissions=True)
	for doctype in ("GRN Entry Detail", "GRN Note"):
		frappe.clear_cache(doctype=doctype)
