# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Paddy Release from DCRO. DCRO portal, Delivery Certificate > Miller RO PDS (Add page):
the miller's paddy release history, read after Show, Save or a click on the history (dvmillerhistory).
Paddy Lifted and Paddy Released are shown per district: Own District as the mill's District
in Mill Master, an other district by its District Master name in the portal header
(e.g. "(Other District)KORAPUT"). After each district's Paddy Released: its Remaining Balance =
Paddy Lifted of that district (on the portal a running total up to that order) - the sum of
its Paddy Released of all orders of the mill and Season (Kharif / Rabi) up to and including that date;
rejected or cancelled orders release nothing (see procurement/dcro_paddy_release.py).
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.dcro_paddy_release import district_cells
from ivri_od.procurement.portal_report import section_report

SECTION = "Paddy Release"
DATE_COLUMN = "Date of Requistion"  # spelt as on the portal
# Words of the Paddy Lifted / Released columns (Stock Account for Paddy, manual entry).
BALANCE = {
	"label": "Remaining Balance",
	"lifted": ("paddy lifted",),
	"released": ("paddy released",),
	"skip_status": ("reject", "cancel"),
}


def execute(filters=None):
	return section_report(filters, SECTION, site="DCRO", date_column=DATE_COLUMN, transform=district_cells)
