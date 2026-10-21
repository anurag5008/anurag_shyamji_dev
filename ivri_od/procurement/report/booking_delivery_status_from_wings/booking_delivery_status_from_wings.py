# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Booking Delivery Status from WINGS. WINGS portal (fciarms.in), Mill > e_tec (Booking / Delivery Status, table DataTables_Table_0),
read as soon as the page opens. KMS Year comes from the page address (cyear).
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "Booking / Delivery Status"


def execute(filters=None):
	return section_report(filters, SECTION, site="WINGS")
