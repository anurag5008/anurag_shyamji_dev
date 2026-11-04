# Copyright (c) 2026, Profezzo and contributors
"""Joint Custody and Maintenance Charge Report: custody and maintenance charges payable to a
miller for one KMS Year, from the average paddy stock the mill held each month.

KMS Year "24-25" runs from 01-11-2024 to 31-10-2025. One row per month from From Month to To Month
(any months, any year; each month counted whole). Movements before From Month make the Opening Balance.

Columns of a month:
- Opening Balance: Closing Balance of the month before (November: stock before 1 November).
- Receipt - Transfer from other Mill: submitted Mill Paddy Transfer entries (manual) of the mill
  and District, by Transfer Date.
- Receipt - PACS: paddy procured: PPAS Transit Pass quantity of the mill and KMS Year whose PPC is
  in the District (PPC Master), by Transit Pass Date (same as Stock Account for Paddy, PACs + WSHGs).
- Total = Opening Balance + Transfer + PACS.
- Issued for Milling: Paddy Stock Register's Issue for Milling (date-wise), summed for the month.
- Closing Balance = Total - Issued for Milling.
- OB+CB = Opening Balance + Closing Balance; OB+CB/2 = (Opening Balance + Closing Balance) / 2.

All data sources are read in ``get_movements``."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate

from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	get_issue_for_milling,
	get_kms_seasons,
	get_kms_years,
	get_message,
	get_months,
	get_transit_passes,
	tp_receipts,
)

PRECISION = 2
AVG_PRECISION = 3
# Rate per Qtl per month. ASSUMPTION: fixed at 2.40 until the client confirms where it comes from.
RATE_PER_QTL_PER_MONTH = 2.40

RECEIPTS = ("transfer", "pacs")
ISSUE = "issue"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = validate_filters(filters)
	months = get_months(from_date, to_date)

	opening, movements, skipped_passes = get_movements(filters, from_date, to_date)
	rows = build_rows(months, opening, movements)
	summary = get_summary(rows, RATE_PER_QTL_PER_MONTH)
	data = [*rows, get_total_row(rows)]

	message = get_message(skipped_passes, frappe._dict(mill=filters.mill))
	return get_columns(), data, message, None, get_report_summary(summary)


def validate_filters(filters):
	"""Returns (1st day of From Month, last day of To Month)."""
	for fieldname, label in (
		("mill", _("Mill No")),
		("kms_year", _("KMS Year")),
		("district", _("District")),
		("from_month", _("From Month")),
		("to_month", _("To Month")),
	):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is mandatory").format(label))

	if filters.kms_year not in get_kms_years():
		frappe.throw(_("KMS Year {0} is not in Season Master").format(filters.kms_year))

	from_date = getdate(get_first_day(filters.from_month))
	to_date = getdate(get_last_day(filters.to_month))
	if from_date > to_date:
		frappe.throw(_("From Month must be before To Month"))
	return from_date, to_date


def get_kms_months(kms_year) -> list[date]:
	"""First day of each month of the KMS Year: "24-25" -> 01-11-2024 ... 01-10-2025."""
	start = date(2000 + int(kms_year.split("-")[0]), 11, 1)
	return [getdate(add_months(start, i)) for i in range(12)]


def get_movements(filters, from_date, to_date):
	"""THE ONLY PLACE THAT READS DATA.

	Returns ``(opening, movements, skipped_passes)``:
	- ``opening``: paddy (Qtl) held before ``from_date`` (1st of From Month).
	- ``movements``: ``{first day of month: {"transfer": qty, "pacs": qty, "issue": qty}}``.
	- ``skipped_passes``: Transit Passes of the mill not counted (PPC not in PPC Master / no District).
	"""
	paddy_filters = frappe._dict(mill=filters.mill, kms_year=filters.kms_year, paddy_account=filters.district)

	passes, skipped_passes = get_transit_passes(paddy_filters, get_kms_seasons(filters.kms_year), to_date)
	entries = [(day, "pacs", qty) for day, _column, qty in tp_receipts(passes)]  # PACS + WSHG procured
	entries += get_transfers(filters, to_date)
	entries += [(day, ISSUE, qty) for day, _column, qty in get_issue_for_milling(paddy_filters, to_date)]

	opening, movements = 0.0, defaultdict(lambda: defaultdict(float))
	for day, column, qty in entries:
		if day > to_date:
			continue
		if day < from_date:
			opening += -qty if column == ISSUE else qty
		else:
			movements[day.replace(day=1)][column] += qty
	return opening, movements, skipped_passes


def get_transfers(filters, to_date):
	"""(Transfer Date, "transfer", qty) of submitted Mill Paddy Transfer entries of the mill and District."""
	rows = frappe.get_all(
		"Mill Paddy Transfer",
		filters={
			"docstatus": 1,
			"mill": filters.mill,
			"district": filters.district,
			"transfer_date": ["<=", to_date],
		},
		fields=["transfer_date", "quantity"],
		limit_page_length=0,
	)
	return [(getdate(row.transfer_date), "transfer", flt(row.quantity)) for row in rows]


def build_rows(months, opening, movements) -> list[dict]:
	rows, ob = [], flt(opening, PRECISION)
	for month in months:
		moved = movements.get(month, {})
		transfer = flt(moved.get("transfer"), PRECISION)
		pacs = flt(moved.get("pacs"), PRECISION)
		issue = flt(moved.get(ISSUE), PRECISION)
		total = flt(ob + transfer + pacs, PRECISION)
		cb = flt(total - issue, PRECISION)
		ob_cb = flt(ob + cb, PRECISION)
		rows.append(
			{
				"month": month.strftime("%b-%y"),
				"ob": ob,
				"transfer": transfer,
				"pacs": pacs,
				"total": total,
				"issue": issue,
				"cb": cb,
				"ob_cb": ob_cb,
				"ob_cb_half": flt(ob_cb / 2, AVG_PRECISION),
			}
		)
		ob = cb
	return rows


def get_total_row(rows) -> dict:
	"""Opening Balance, Total and Closing Balance are balances: their sum has no meaning, so blank."""
	total = {"month": _("Total"), "bold": 1, "ob": None, "total": None, "cb": None}
	for fieldname, precision in (
		("transfer", PRECISION),
		("pacs", PRECISION),
		("issue", PRECISION),
		("ob_cb", PRECISION),
		("ob_cb_half", AVG_PRECISION),
	):
		total[fieldname] = flt(sum(row[fieldname] for row in rows), precision)
	return total


def get_summary(rows, rate) -> dict:
	"""A to E of the paper statement. No receipt (B = 0): everything is 0, no division error."""
	average_paddy = flt(sum(row["ob_cb_half"] for row in rows), PRECISION)  # A
	received = flt(sum(row["transfer"] + row["pacs"] for row in rows), PRECISION)  # B
	average_period = flt(average_paddy / received, AVG_PRECISION) if received else 0.0  # C
	due_per_qtl = flt(average_period * flt(rate), PRECISION)  # D
	payable = flt(round(due_per_qtl * received), PRECISION)  # E, nearest rupee
	return {
		"average_paddy": average_paddy,
		"received": received,
		"average_period": average_period,
		"due_per_qtl": due_per_qtl,
		"payable": payable,
	}


def get_report_summary(summary) -> list[dict]:
	return [
		{"label": _("A. Total Average Paddy (Qtl)"), "value": summary["average_paddy"], "datatype": "Float"},
		{"label": _("B. Total Paddy Received (Qtl)"), "value": summary["received"], "datatype": "Float"},
		{"label": _("C. Total Average Period (Months)"), "value": summary["average_period"], "datatype": "Float"},
		{"label": _("D. Custody Maintenance Due (per Qtl)"), "value": summary["due_per_qtl"], "datatype": "Float"},
		{
			"label": _("E. Joint & Custody Maintenance Payable to Miller"),
			"value": summary["payable"],
			"datatype": "Currency",
			"currency": "INR",
			"indicator": "Green",
		},
	]


def get_columns():
	columns = [{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 90}]
	for label, fieldname, precision, width in (
		(_("Opening Balance"), "ob", PRECISION, 140),
		(_("Receipt - Transfer from other Mill"), "transfer", PRECISION, 200),
		(_("Receipt - PACS"), "pacs", PRECISION, 140),
		(_("Total"), "total", PRECISION, 130),
		(_("Issued for Milling"), "issue", PRECISION, 150),
		(_("Closing Balance"), "cb", PRECISION, 140),
		(_("OB+CB"), "ob_cb", PRECISION, 130),
		(_("OB+CB/2"), "ob_cb_half", AVG_PRECISION, 130),
	):
		columns.append(
			{"label": label, "fieldname": fieldname, "fieldtype": "Float", "precision": precision, "width": width}
		)
	return columns
