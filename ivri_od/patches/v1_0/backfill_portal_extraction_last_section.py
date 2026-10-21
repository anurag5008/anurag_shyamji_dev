# Copyright (c) 2026, Profezzo and contributors
"""Portal Data Extraction "Last Section" (list column): the section of each extraction's latest run."""

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "portal_data_extraction")
	for row in frappe.db.sql(
		"""select parent, section from `tabPortal Extraction Run` r
		where r.parenttype = 'Portal Data Extraction' and r.extracted_on = (
			select max(r2.extracted_on) from `tabPortal Extraction Run` r2 where r2.parent = r.parent)""",
		as_dict=True,
	):
		frappe.db.set_value("Portal Data Extraction", row.parent, "last_section", row.section, update_modified=False)
