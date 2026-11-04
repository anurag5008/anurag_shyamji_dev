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
Quantity (Qtl) = Lots x Lot Quantity of Rice Lot Quantity (e.g. 1 lot x 290 = 290); blank
when the lots are not read yet.
Filters as Stock Account for Paddy, all optional (empty when the report opens: every DC):
Mill Name, KMS Year (the row's "KMS (Year)"; only the years of the mill's View DC rows),
District (the row's District), From Month - To Month (the row's "Generated Date", from the
first day of From Month to the last day of To Month).
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, getdate

from ivri_od.procurement.portal_report import _load, section_report
from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	dcro_kms_year,
	kms_year_label,
	parse_portal_date,
	season_master_year,
)

SECTION = "View DC"
KMS_COLUMN = "KMS (Year)"
DISTRICT_COLUMN = "District"
DATE_COLUMN = "Generated Date"
# (column, words of the detail header to add up, fieldtype): the number of lots read by the agent.
LOT_TOTALS = [("Lots", ["lots"], "Int")]


QUANTITY_FIELD = "qty"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns, data, *rest = section_report(
		filters,
		SECTION,
		site="DCRO",
		details=True,
		receipt_columns=["RRC", "FCI"],
		detail_totals=LOT_TOTALS,
		row_filter=dc_filter(filters),
	)
	add_quantity(columns, data)
	return (columns, data, *rest)


def dc_filter(filters):
	"""Keep the DCs of the KMS Year and District generated from From Month to To Month."""
	year = int(season_master_year(filters.kms_year)) if filters.kms_year else None
	district = (filters.district or "").strip().lower()
	from_date = getdate(get_first_day(filters.from_month)) if filters.from_month else None
	to_date = getdate(get_last_day(filters.to_month)) if filters.to_month else None
	if from_date and to_date and from_date > to_date:
		frappe.throw(_("From Month must be before To Month"))

	def keep(record, cells):
		if year and dcro_kms_year(cells.get(KMS_COLUMN)) != year:
			return False
		if district and (cells.get(DISTRICT_COLUMN) or "").strip().lower() != district:
			return False
		if from_date or to_date:
			generated = parse_portal_date(cells.get(DATE_COLUMN))
			if not generated or (from_date and generated < from_date) or (to_date and generated > to_date):
				return False
		return True

	return keep


@frappe.whitelist()
def get_kms_years(mill=None):
	"""KMS Years ("25-26") of the View DC rows, newest first; with ``mill`` only that mill's rows."""
	conditions = {"site": "DCRO", "section": SECTION}
	if mill:
		conditions["mill_id"] = mill
	years = set()
	for row_data in frappe.get_list("Portal Record", filters=conditions, pluck="row_data", limit_page_length=0):
		year = dcro_kms_year(_load(row_data).get(KMS_COLUMN))
		if year:
			years.add(year)
	return [kms_year_label(year) for year in sorted(years, reverse=True)]


def add_quantity(columns, data):
	"""Quantity (Qtl) column after Lots: Lots x Rice Lot Quantity."""
	lots_field = next((c["fieldname"] for c in columns if c.get("label") == _("Lots")), None)
	if not lots_field:
		return
	at = next(i for i, c in enumerate(columns) if c["fieldname"] == lots_field) + 1
	columns.insert(
		at,
		{"fieldname": QUANTITY_FIELD, "label": _("Quantity (Qtl)"), "fieldtype": "Float", "precision": 2, "width": 120},
	)
	lot_quantity = flt(frappe.db.get_single_value("Rice Lot Quantity", "lot_quantity"))
	for row in data:
		lots = row.get(lots_field)
		row[QUANTITY_FIELD] = None if lots is None else flt(lots) * lot_quantity
