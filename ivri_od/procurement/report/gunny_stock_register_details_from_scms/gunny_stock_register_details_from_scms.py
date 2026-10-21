# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Gunny Stock Register Details from SCMS. SCMS Jute Gunny Bags Misc Report: the Gunny Stock Register Details table, one row per date (key "Date - A").
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "Gunny Stock Register Details"


def execute(filters=None):
	return section_report(filters, SECTION, date_column="Date - A")
