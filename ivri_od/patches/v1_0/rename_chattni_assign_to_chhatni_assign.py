"""Rename Chattni Assign DocType to Chhatni Assign."""

import frappe


def execute():
	old_name = "Chattni Assign"
	new_name = "Chhatni Assign"
	if frappe.db.exists("DocType", old_name) and not frappe.db.exists("DocType", new_name):
		frappe.rename_doc("DocType", old_name, new_name, force=True)

	if frappe.db.exists("DocType", "Target Allocation"):
		frappe.db.set_value(
			"DocField",
			{"parent": "Target Allocation", "fieldname": "latest_chutney_assign"},
			{
				"options": new_name,
				"label": "Latest Chhatni Assign",
				"description": "From the latest Chhatni Assign for this PPC and Mill.",
			},
		)

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
			(new_name, new_name, old_name),
		)

	frappe.reload_doc("procurement", "doctype", "chhatni_assign")
	frappe.reload_doc("procurement", "doctype", "target_allocation")
	frappe.clear_cache(doctype=new_name)
	frappe.clear_cache(doctype="Target Allocation")
