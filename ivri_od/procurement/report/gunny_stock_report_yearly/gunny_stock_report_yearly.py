# Copyright (c) 2026, Profezzo and contributors
"""Gunny Stock Report Yearly: month-wise stock account of NEW and OLD gunny bags for one KMS Year
and one District account. Filters as Stock Account for Paddy.

- Qtl of Paddy Procurement: TP quantity of the mill's PPAS Transit Passes of the KMS Year whose PPC
  is in the District (PPC Master), by Transit Pass Date month (PACs + WSHGs of Stock Account for Paddy).
- OSCSC: SCMS Gunny Stock Register Details of the mill, columns C + D + E (as New NBT Gunny Account).
  The register has no District (one gunny stock per mill), so OSCSC is shown only in the account of
  the mill's own District (Mill Master); other Districts get gunny only by Tr. Receipt, OSCSC 0.
  A mill without a District shows OSCSC in every District.
- No. of New Bags Used for CMR: lots delivered in the District x No. of Bags per Lot (as the Issue
  of the District in New NBT Gunny Account).
- Typed in the report (Edit, then click a cell; saved in Gunny Stock Yearly Entry): Tr. Receipt, Actual
  Cost of Old Bags Procured, Tr. Issue, Old Bags Procured from CKMS, Old Bags Used in Current KMS and
  Actual Cost of Unused Bags.
- Tr. Receipt also gets every Tr. Issue typed for the mill in the same month, of any District and
  KMS Year (one gunny stock per mill: bags sent to another account come in there the same month), except the Tr. Issues of this
  same KMS Year and District. Row: tr_receipt = tr_receipt_typed + tr_receipt_transfer.
- OSCSC OB = New Bags Remained Unused of the month before;
  New Bags Remained Unused = OSCSC OB + OSCSC + Tr. Receipt - Tr. Issue - New Bags Used for CMR.
- Old Bags Carried Over from PY = Old Bags Remained Unused of the month before;
  Old Bags Remained Unused = Carried Over + Procured from CKMS - Used in Current KMS.
Balances run from the KMS Year start (Season Master Start Date), so the first month shown carries
the months before From Month. Total row: sums of Qtl of Paddy Procurement, New Bags Used for CMR and
Old Bags Used in Current KMS; balance columns blank. Columns 10-11 are grouped under "No of old bags
in stock" in the print (gunny_stock_report_yearly.html)."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, getdate

from ivri_od.procurement.report.new_nbt_gunny_account.new_nbt_gunny_account import (
	issue_movements,
	kms_start,
	register_movements,
)
from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	get_kms_seasons,
	get_kms_years,
	get_months,
	get_transit_passes,
	season_master_year,
	validate_filters,
)

PRECISION = 2
TOTAL_COLUMNS = ("paddy_qtl", "new_used_cmr", "old_used")
# Columns typed in the report: fieldname -> Gunny Stock Yearly Entry "Column".
MANUAL_COLUMNS = {
	"tr_receipt": "Tr. Receipt",
	"old_bag_rate": "Actual Cost of Old Bags Procured",
	"tr_issue": "Tr. Issue",
	"old_procured": "Old Bags Procured from CKMS",
	"old_used": "Old Bags Used in Current KMS",
	"unused_cost": "Actual Cost of Unused Bags",
}
AMOUNT_COLUMNS = ("old_bag_rate", "unused_cost")
BAG_COLUMNS = ("oscsc", "tr_receipt", "tr_issue", "new_used_cmr", "old_procured", "old_used")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = validate_filters(filters)

	if filters.kms_year not in get_kms_years(filters.mill):
		# No Transit Pass of the mill in the KMS Year: no statement.
		return get_columns(), [], _("Mill {0} has no Transit Pass data in KMS Year {1}.").format(
			filters.mill, filters.kms_year
		)

	start = kms_start(cint(season_master_year(filters.kms_year)))
	first_month = getdate(get_first_day(min(start, from_date) if start else from_date))
	movements = get_movements(filters, start, to_date)
	rows = build_rows(get_months(first_month, to_date), movements)
	# Months before From Month only carry their balances into the first month shown.
	shown = rows[len(get_months(first_month, from_date)) - 1 :]
	shown.append(get_total_row(shown))
	return get_columns(), shown


def get_columns():
	columns = [{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 90}]
	for label, fieldname, fieldtype, width in (
		(_("Qtl of Paddy Procurement"), "paddy_qtl", "Float", 140),
		(_("OSCSC OB"), "oscsc_ob", "Int", 100),
		(_("OSCSC"), "oscsc", "Int", 100),
		(_("Tr. Receipt"), "tr_receipt", "Int", 110),
		(_("Actual Cost of Old Bags Procured"), "old_bag_rate", "Currency", 150),
		(_("Tr. Issue"), "tr_issue", "Int", 110),
		(_("No. of New Bags Used for CMR"), "new_used_cmr", "Int", 140),
		(_("Nos of New Bags Remained Unused"), "new_unused", "Int", 150),
		(_("Old Bags - Carried Over from PY"), "old_carried", "Int", 150),
		(_("Old Bags - Procured from CKMS"), "old_procured", "Int", 150),
		(_("No. of Old Bags Used in Current KMS"), "old_used", "Int", 160),
		(_("No. of Old Bags Remained Unused"), "old_unused", "Int", 150),
		(_("Actual Cost of Unused Bags"), "unused_cost", "Currency", 150),
	):
		column = {"label": label, "fieldname": fieldname, "fieldtype": fieldtype, "width": width}
		if fieldtype == "Float":
			column["precision"] = PRECISION
		columns.append(column)
	return columns


def get_movements(filters, start, to_date):
	"""{month: {column: value}} of the mill, KMS Year and District up to To Month."""
	movements = defaultdict(lambda: defaultdict(float))
	seasons = get_kms_seasons(filters.kms_year)

	passes, _skipped = get_transit_passes(filters, seasons, to_date)
	for tp in passes:
		if tp.transit_pass_date:
			movements[getdate(tp.transit_pass_date).replace(day=1)]["paddy_qtl"] += flt(tp.quantity)

	if shows_oscsc(filters):
		for row_date, column, _district, _type, bags in register_movements(filters.mill, start, to_date):
			if column == "receipts":
				movements[getdate(row_date).replace(day=1)]["oscsc"] += bags

	year = cint(season_master_year(filters.kms_year))
	for lot_date, _column, district, _type, bags in issue_movements(filters.mill, year, to_date):
		if district == filters.paddy_account:
			movements[getdate(lot_date).replace(day=1)]["new_used_cmr"] += bags

	for entry in frappe.get_all(
		"Gunny Stock Yearly Entry",
		filters={
			"mill": filters.mill,
			"kms_year": filters.kms_year,
			"district": filters.paddy_account,
			"month": ["<=", to_date],
		},
		fields=["month", "report_column", "value"],
	):
		fieldname = {label: key for key, label in MANUAL_COLUMNS.items()}.get(entry.report_column)
		if fieldname:
			movements[getdate(entry.month)][fieldname] += flt(entry.value)

	for month, bags in transfer_receipts(filters, to_date):
		movements[month]["tr_receipt_transfer"] += bags
	return movements


def shows_oscsc(filters):
	"""OSCSC (government gunny of the mill) only in the account of the mill's own District, so it is
	not counted again in every District; the others get gunny by Tr. Receipt."""
	home_district = frappe.db.get_value("Mill Master", filters.mill, "district")
	return not home_district or home_district == filters.paddy_account


def transfer_receipts(filters, to_date):
	"""(month, bags): the Tr. Issues of the mill, any District and KMS Year but this account (KMS Year
	and District of the filters), as receipts of the same month (up to To Month)."""
	receipts = []
	for entry in frappe.get_all(
		"Gunny Stock Yearly Entry",
		filters={
			"mill": filters.mill,
			"report_column": MANUAL_COLUMNS["tr_issue"],
			"month": ["<=", to_date],
		},
		fields=["kms_year", "district", "month", "value"],
	):
		if (entry.kms_year, entry.district) != (filters.kms_year, filters.paddy_account):
			receipts.append((getdate(entry.month), cint(entry.value)))
	return receipts


def build_rows(months, movements):
	"""One row per month (months without movements too, balances carried forward). A month row also
	carries its first day (month_date), for typing values in the report."""
	rows = []
	new_balance = old_balance = 0
	for month in months:
		month_movements = movements.get(month) or {}
		row = {
			"month": month.strftime("%b-%y"),
			"month_date": str(month),
			"paddy_qtl": flt(month_movements.get("paddy_qtl"), PRECISION),
		}
		for column in BAG_COLUMNS:
			row[column] = cint(month_movements.get(column))
		for column in AMOUNT_COLUMNS:
			row[column] = flt(month_movements.get(column), PRECISION)
		# Typed Tr. Receipt (what Edit changes) + Tr. Issues of other accounts in the same month.
		row["tr_receipt_typed"] = row["tr_receipt"]
		row["tr_receipt_transfer"] = cint(month_movements.get("tr_receipt_transfer"))
		row["tr_receipt"] += row["tr_receipt_transfer"]

		row["oscsc_ob"] = new_balance
		row["new_unused"] = new_balance + row["oscsc"] + row["tr_receipt"] - row["tr_issue"] - row["new_used_cmr"]
		row["old_carried"] = old_balance
		row["old_unused"] = old_balance + row["old_procured"] - row["old_used"]

		new_balance, old_balance = row["new_unused"], row["old_unused"]
		rows.append(row)
	return rows


def get_total_row(month_rows):
	# notes: the "NB:" lines printed below the table (Transfer Receipts / Issues; no source yet).
	total_row = {"month": _("Total"), "bold": 1, "notes": []}
	for column in TOTAL_COLUMNS:
		total = sum(row[column] for row in month_rows)
		total_row[column] = flt(total, PRECISION) if column == "paddy_qtl" else total
	return total_row


@frappe.whitelist(methods=["POST"])
def set_value(mill: str, kms_year: str, district: str, month: str, fieldname: str, value: float | None = None) -> float:
	"""Save one typed cell of the report (Gunny Stock Yearly Entry); empty or 0 removes it. Returns the value saved."""
	column = MANUAL_COLUMNS.get(fieldname)
	if not column:
		frappe.throw(_("This column cannot be typed in"))
	frappe.has_permission("Gunny Stock Yearly Entry", "create", throw=True)
	if not frappe.db.exists("Mill Master", mill):
		frappe.throw(_("Mill {0} is not in Mill Master").format(mill))
	if not frappe.db.exists("District Master", district):
		frappe.throw(_("District {0} is not available in District Master").format(frappe.bold(district or "")))
	value = flt(value, PRECISION)
	if value < 0:
		frappe.throw(_("The value cannot be negative"))

	month = getdate(get_first_day(month))
	key = {"mill": mill, "kms_year": kms_year, "district": district, "month": month, "report_column": column}
	name = frappe.db.exists("Gunny Stock Yearly Entry", key)
	if not value:
		if name:
			frappe.delete_doc("Gunny Stock Yearly Entry", name)
		return 0
	doc = frappe.get_doc("Gunny Stock Yearly Entry", name) if name else frappe.new_doc("Gunny Stock Yearly Entry")
	doc.update({**key, "value": value})
	doc.save()
	return doc.value
