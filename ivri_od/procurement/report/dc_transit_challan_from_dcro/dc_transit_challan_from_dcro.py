# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""DC Transit Challan from DCRO. DCRO portal, Billing System > AC Note Bill > DC Transit
Challan View (table gvDCDetails), read after Show. For every row the agent saves the
file of the Details button and of the AC Note Doc button; each has its own download column.
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "DC Transit Challan"
# Column headers of the document buttons on the portal (also the section's Receipt Link Text).
DOCUMENTS = ["Details", "AC Note Doc"]


def execute(filters=None):
	return section_report(filters, SECTION, site="DCRO", document_columns=DOCUMENTS)
