"""The Rice Dispatch Summary report is now called Rice Dispatch.

A standard report's name is its key, so the old definition is dropped once the new one exists (it is only
the report's definition: no weighment data, filters or saved lists are involved).
"""

import frappe

OLD_NAME = "Rice Dispatch Summary"
NEW_NAME = "Rice Dispatch"


def execute():
	frappe.reload_doc("procurement", "report", "rice_dispatch")
	if not frappe.db.exists("Report", NEW_NAME):
		return  # keep the old definition until the new one is in place
	if frappe.db.exists("Report", OLD_NAME):
		frappe.db.delete("Has Role", {"parent": OLD_NAME, "parenttype": "Report"})
		frappe.db.delete("Report", {"name": OLD_NAME})
	frappe.clear_cache()
