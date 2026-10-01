"""Reload Target Allocation with latest chutney fields."""

from __future__ import annotations

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	path = os.path.join(
		frappe.get_app_path("ivri_od"),
		"procurement",
		"doctype",
		"target_allocation",
		"target_allocation.json",
	)
	if os.path.exists(path):
		import_file_by_path(path, force=True, ignore_version=True)
	frappe.clear_cache()
