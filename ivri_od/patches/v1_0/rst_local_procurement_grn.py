"""RST local procurement → farmer/agent WBM and GRN without transit pass."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	app_path = frappe.get_app_path("ivri_od")
	for folder, filename in (
		("grn_note", "grn_note.json"),
	):
		path = os.path.join(app_path, "procurement", "doctype", folder, filename)
		if os.path.exists(path):
			import_file_by_path(path, force=True, ignore_version=True)
	frappe.clear_cache()
