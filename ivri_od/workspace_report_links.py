# Copyright (c) 2026, Profezzo and contributors

"""Ensure workspace report links open the query-report view (table), not Report setup."""


def patch_workspace_report_links():
	from frappe.desk.desktop import Workspace

	if getattr(Workspace, "_ivri_od_query_report_patch", False):
		return

	original_prepare = Workspace._prepare_item

	def _prepare_item(self, item):
		prepared = original_prepare(self, item)
		link_type = prepared.get("link_type")
		link_to = prepared.get("link_to")
		if link_type == "Report" and link_to:
			import frappe

			report_type = prepared.get("report_type")
			if not report_type:
				report_type = frappe.db.get_value("Report", link_to, "report_type")
			if report_type in ("Query Report", "Script Report", "Custom Report"):
				prepared["is_query_report"] = 1
		return prepared

	Workspace._prepare_item = _prepare_item
	Workspace._ivri_od_query_report_patch = True
