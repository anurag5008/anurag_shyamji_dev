# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""RRC DC Summary from SCMS. SCMS DC Monitoring: one row per DC. Click DC NO. to see its lots.
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "DC Monitoring"


def execute(filters=None):
	return section_report(filters, SECTION, details=True)
