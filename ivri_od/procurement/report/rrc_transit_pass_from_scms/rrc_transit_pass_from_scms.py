# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""RRC Transit Pass from SCMS. SCMS Transit Challan (RRC): one row per challan, with the challan PDF saved from the Action (eye) button.
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from frappe import _

from ivri_od.procurement.portal_report import section_report

SECTION = "Transit Challan RRC"


def execute(filters=None):
	return section_report(filters, SECTION, receipt_label=_("Challan"))
