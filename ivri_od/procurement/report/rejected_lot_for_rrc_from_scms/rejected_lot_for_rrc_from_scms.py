# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Rejected Lot for RRC from SCMS. SCMS Search Lot page, Rejected Lot for RRC tab.
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "Rejected Lot for RRC"


def execute(filters=None):
	return section_report(filters, SECTION)
