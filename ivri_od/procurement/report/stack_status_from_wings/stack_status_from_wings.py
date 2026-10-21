# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Stack Status from WINGS. WINGS portal (fciarms.in), Mill > Tagging (Stack Status),
the table in div#rept_div, read after View. The search filters on the page are saved
as columns of every row (section "Page Filter Columns" = *).
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "Stack Status"


def execute(filters=None):
	return section_report(filters, SECTION, site="WINGS")
