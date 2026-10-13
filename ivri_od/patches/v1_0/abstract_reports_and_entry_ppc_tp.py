"""Abstract Report (rename Mill PPC), Abstract Physical report, Entry PPC/TP fields."""

import frappe

from ivri_od.procurement.procurement_reports import ensure_standard_procurement_reports
from ivri_od.procurement.procurement_workspace import sync_procurement_desk_ui


OLD_REPORT = "Mill PPC Season Quantity Summary"
NEW_REPORT = "Abstract Report"


def execute():
	_migrate_report_name()
	ensure_standard_procurement_reports()
	_migrate_workspace_links()
	sync_procurement_desk_ui()


def _migrate_report_name():
	if frappe.db.exists("Report", OLD_REPORT) and not frappe.db.exists("Report", NEW_REPORT):
		frappe.rename_doc("Report", OLD_REPORT, NEW_REPORT, force=True, merge=False)
	elif frappe.db.exists("Report", OLD_REPORT) and frappe.db.exists("Report", NEW_REPORT):
		frappe.delete_doc("Report", OLD_REPORT, force=True, ignore_permissions=True)

	frappe.db.sql(
		"""
		UPDATE `tabWorkspace Link`
		SET link_to = %s, label = 'Abstract Report'
		WHERE link_to = %s AND link_type = 'Report'
		""",
		(NEW_REPORT, OLD_REPORT),
	)
	frappe.db.sql(
		"""
		UPDATE `tabWorkspace Shortcut`
		SET link_to = %s, label = 'Abstract Report'
		WHERE link_to = %s AND type = 'Report'
		""",
		(NEW_REPORT, OLD_REPORT),
	)

	abstract_url = "/app/query-report/Abstract%20Report"
	frappe.db.sql(
		"""
		UPDATE `tabWorkspace Sidebar Item`
		SET label = 'Abstract Report', url = %s
		WHERE url LIKE %s OR label = 'Mill PPC Season Qty'
		""",
		(abstract_url, "%Mill%20PPC%20Season%"),
	)
	frappe.db.commit()


def _migrate_workspace_links():
	pass
