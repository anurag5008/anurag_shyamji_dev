# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""TEC Report from WINGS. WINGS portal (fciarms.in), ETec > Miller TEC Report, the
table in div#report_div, read after View. For every row the agent opens the button of
the "Delivered" column and saves its table as the record's detail rows. Click the
first column to see them, or tick "Show Detail Rows".
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "TEC Report"


def execute(filters=None):
	return section_report(filters, SECTION, site="WINGS", details=True)
