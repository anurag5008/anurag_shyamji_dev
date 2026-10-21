# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Paddy Release from DCRO. DCRO portal, Delivery Certificate > Miller RO PDS (Add page):
the miller's paddy release history, read after Show, Save or a click on the history (dvmillerhistory).
Remaining Balance = Paddy Lifted (on the portal a running total up to that order)
- the sum of Paddy Released of all orders up to and including that date.
Own and other district columns are added up; rejected or cancelled orders release nothing.
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "Paddy Release"
DATE_COLUMN = "Date of Requistion"  # spelt as on the portal
BALANCE = {
	"label": "Remaining Balance",
	"lifted": ("paddy lifted",),
	"released": ("paddy released",),
	"skip_status": ("reject", "cancel"),
}


def execute(filters=None):
	return section_report(filters, SECTION, site="DCRO", date_column=DATE_COLUMN, balance=BALANCE)
