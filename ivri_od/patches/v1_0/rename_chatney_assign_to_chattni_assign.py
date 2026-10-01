"""Rename Chatney Assign DocType to Chhatni Assign (legacy intermediate: Chattni Assign)."""

import frappe


def execute():
	old_name = "Chatney Assign"
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

	frappe.reload_doc("procurement", "doctype", "chhatni_assign")
	frappe.reload_doc("procurement", "doctype", "target_allocation")
	frappe.clear_cache(doctype=new_name)
	frappe.clear_cache(doctype="Target Allocation")
