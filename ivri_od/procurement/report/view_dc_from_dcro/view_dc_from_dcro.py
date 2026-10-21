# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""View DC from DCRO. DCRO portal, View DC page: one row per DC, with the search
filters (saved as columns of every row) so a DC can be traced to the search it came from.
Document: the PDF saved from the row's View_RRC/View_FCI button, linked on that RRC or FCI cell.
Lots: when the agent opens that DC page, before it clicks Print it reads the number
of lots, td[4] of each row of grdDepotFCIbody (FCI) or grdDepotRRCbody (RRC)
(Portal Site Section "Detail Table ID" = "grdDepotFCIbody[4], grdDepotRRCbody[4]"),
saved as the row's detail rows {DC Type, Lots}. The "Lots" column is their sum;
"Show Detail Rows" lists each line.
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

from ivri_od.procurement.portal_report import section_report

SECTION = "View DC"
# (column, words of the detail header to add up, fieldtype): the number of lots read by the agent.
LOT_TOTALS = [("Lots", ["lots"], "Int")]


def execute(filters=None):
	return section_report(
		filters,
		SECTION,
		site="DCRO",
		details=True,
		receipt_columns=["RRC", "FCI"],
		detail_totals=LOT_TOTALS,
	)
