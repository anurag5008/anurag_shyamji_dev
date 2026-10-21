# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Lot Search from SCMS. SCMS Search Lot page, Lot Search tab, with the PDF of each row's Print button.
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from frappe import _

from ivri_od.procurement.portal_report import section_report

SECTION = "Lot Search"


def execute(filters=None):
	return section_report(filters, SECTION, receipt_label=_("Print"))
