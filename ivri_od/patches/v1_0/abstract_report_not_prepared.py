"""Abstract Report must run live, not as a Prepared Report.

It was set to "Prepared Report" in the desk, so the report showed the numbers saved when it was last
prepared (October) and ignored every change of the report. It runs in under a second, so it runs live."""

import frappe

REPORT = "Abstract Report"


def execute():
	if frappe.db.exists("Report", REPORT):
		frappe.db.set_value("Report", REPORT, "prepared_report", 0)
	for name in frappe.get_all("Prepared Report", filters={"report_name": REPORT}, pluck="name"):
		frappe.delete_doc("Prepared Report", name, ignore_permissions=True, force=True)
	frappe.clear_cache()
