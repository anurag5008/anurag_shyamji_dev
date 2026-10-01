"""Ensure Chhatni Assign exists in DB and remove stale Chatney Assign module path."""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


OLD_NAME = "Chatney Assign"
NEW_NAME = "Chhatni Assign"


def execute():
	_chhatni_json = os.path.join(
		frappe.get_app_path("ivri_od"),
		"procurement",
		"doctype",
		"chhatni_assign",
		"chhatni_assign.json",
	)

	if frappe.db.exists("DocType", OLD_NAME) and not frappe.db.exists("DocType", NEW_NAME):
		frappe.rename_doc("DocType", OLD_NAME, NEW_NAME, force=True)
	elif frappe.db.exists("DocType", OLD_NAME) and frappe.db.exists("DocType", NEW_NAME):
		if not frappe.db.count(OLD_NAME):
			frappe.delete_doc("DocType", OLD_NAME, force=True)
		else:
			frappe.rename_doc("DocType", OLD_NAME, NEW_NAME, merge=True, force=True)

	if not frappe.db.exists("DocType", NEW_NAME) and os.path.exists(_chhatni_json):
		import_file_by_path(_chhatni_json, force=True, ignore_version=True)

	_update_link_references()
	_update_target_allocation_link_field()

	if frappe.db.exists("DocType", NEW_NAME):
		frappe.reload_doc("procurement", "doctype", "chhatni_assign")
	if frappe.db.exists("DocType", "Target Allocation"):
		frappe.reload_doc("procurement", "doctype", "target_allocation")

	frappe.clear_cache()


def _update_link_references():
	for doctype in (
		"Workspace Link",
		"Workspace Shortcut",
		"Workspace Sidebar Item",
	):
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		if not meta.has_field("link_to"):
			continue
		frappe.db.sql(
			f"""
			UPDATE `tab{doctype}`
			SET link_to = %s, label = %s
			WHERE link_to = %s
			""",
			(NEW_NAME, NEW_NAME, OLD_NAME),
		)


def _update_target_allocation_link_field():
	if not frappe.db.exists("DocType", "Target Allocation"):
		return
	frappe.db.set_value(
		"DocField",
		{"parent": "Target Allocation", "fieldname": "latest_chutney_assign"},
		{
			"options": NEW_NAME,
			"label": "Latest Chhatni Assign",
			"description": "From the latest Chhatni Assign for this PPC and Mill.",
		},
	)
