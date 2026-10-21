# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Targets Advanced Paddy from WINGS. WINGS portal (fciarms.in), Mill > e_tec (Targets / Advanced Paddy [ FCI DO Procuring : Boiled Non FRK,
Raw Non FRK, Improved Rice ], table DataTables_Table_1), read as soon as the page opens.
KMS Year comes from the page address (cyear).
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "Targets / Advanced Paddy"


def execute(filters=None):
	return section_report(filters, SECTION, site="WINGS")
