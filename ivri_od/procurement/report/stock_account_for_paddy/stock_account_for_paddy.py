# Copyright (c) 2026, Profezzo and contributors
"""Stock Account for Paddy: monthly OB, receipts, milling issue, driage and CB for Civil Supplies."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate
from frappe.utils.nestedset import get_descendants_of

# Paddy Source (Purchase Receipt / Stock Entry) -> receipt column. Blank or anything else goes to Other Rect.
RECEIPT_COLUMNS = {"PACS": "pacs", "WSHG": "wshgs"}
OTHER_RECEIPT_COLUMN = "other_rect"
# Paddy Movement (Stock Entry Type) -> issue column.
ISSUE_COLUMNS = {"Issue for Milling": "issue_for_milling", "Driage": "driage"}

RECEIPTS = ("pacs", "wshgs", "other_rect")
ISSUES = ("issue_for_milling", "driage")
VOUCHER_TYPES = ("Purchase Receipt", "Stock Entry")
PRECISION = 2


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = validate_filters(filters)

	ledger_rows = get_ledger_rows(filters, to_date)
	opening, movements, unclassified = classify(ledger_rows, from_date)
	data = build_rows(get_months(from_date, to_date), opening, movements)

	return get_columns(), data, get_message(ledger_rows, unclassified)


def validate_filters(filters):
	for fieldname, label in (
		("mill", _("Mill Name")),
		("kms_season", _("KMS Year")),
		("paddy_account", _("District")),
		("from_month", _("From Month")),
		("to_month", _("To Month")),
	):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is mandatory").format(label))

	# The mill's company owns the stock; the print heading uses it too.
	filters.company = frappe.db.get_value("Mill Master", filters.mill, "company")
	if not filters.company:
		frappe.throw(_("Set the Company in Mill Master {0}").format(filters.mill))

	from_date = getdate(get_first_day(filters.from_month))
	to_date = getdate(get_last_day(filters.to_month))
	if from_date > to_date:
		frappe.throw(_("From Month must be before To Month"))

	return from_date, to_date


def get_columns():
	columns = [{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 90}]
	for label, fieldname, width in (
		(_("OB"), "ob", 120),
		(_("Receipts - PACs"), "pacs", 140),
		(_("Receipts - WSHGs"), "wshgs", 140),
		(_("Receipts - Other Rect"), "other_rect", 160),
		(_("Total Paddy"), "total_paddy", 130),
		(_("Issue for Milling"), "issue_for_milling", 140),
		(_("Driage"), "driage", 110),
		(_("Total"), "total", 120),
		(_("CB"), "cb", 120),
	):
		columns.append(
			{
				"label": label,
				"fieldname": fieldname,
				"fieldtype": "Float",
				"precision": PRECISION,
				"width": width,
			}
		)
	return columns


def get_ledger_rows(filters, to_date):
	"""Stock ledger rows of paddy vouchers tagged with the selected KMS Season and Paddy Account."""
	sle = frappe.qb.DocType("Stock Ledger Entry")
	rows = []

	for voucher_type in VOUCHER_TYPES:
		voucher = frappe.qb.DocType(voucher_type)
		query = (
			frappe.qb.from_(sle)
			.inner_join(voucher)
			.on(voucher.name == sle.voucher_no)
			.select(
				sle.voucher_type,
				sle.voucher_no,
				sle.item_code,
				sle.posting_date,
				sle.actual_qty,
				sle.stock_uom,
				voucher.paddy_source,
			)
			.where(
				(sle.voucher_type == voucher_type)
				& (sle.is_cancelled == 0)
				& (sle.company == filters.company)
				& (sle.posting_date <= to_date)
				& (voucher.kms_season == filters.kms_season)
				& (voucher.paddy_account == filters.paddy_account)
			)
		)

		if voucher_type == "Stock Entry":
			entry_type = frappe.qb.DocType("Stock Entry Type")
			query = (
				query.left_join(entry_type)
				.on(entry_type.name == voucher.stock_entry_type)
				.select(entry_type.paddy_movement)
			)

		rows.extend(apply_item_and_warehouse(query, sle, filters).run(as_dict=True))

	return rows


def apply_item_and_warehouse(query, sle, filters):
	if filters.item_code:
		query = query.where(sle.item_code == filters.item_code)

	if filters.warehouse:
		warehouses = [filters.warehouse, *get_descendants_of("Warehouse", filters.warehouse)]
		query = query.where(sle.warehouse.isin(warehouses))

	return query


def classify(ledger_rows, from_date):
	"""Return (opening balance, {month: {column: qty}}, unclassified outward vouchers).

	Rows are first netted per voucher, so a transfer between two selected warehouses cancels out.
	Milling and driage count only the paddy that left (negative rows) of their vouchers.
	"""
	vouchers = {}
	for row in ledger_rows:
		key = (row.voucher_type, row.voucher_no, getdate(row.posting_date))
		voucher = vouchers.setdefault(
			key,
			frappe._dict(
				voucher_type=row.voucher_type,
				voucher_no=row.voucher_no,
				posting_date=getdate(row.posting_date),
				paddy_source=row.paddy_source,
				paddy_movement=row.get("paddy_movement"),
				net_qty=0.0,
				out_qty=0.0,
			),
		)
		voucher.net_qty += flt(row.actual_qty)
		if flt(row.actual_qty) < 0:
			voucher.out_qty -= flt(row.actual_qty)

	opening = 0.0
	movements = defaultdict(lambda: defaultdict(float))
	unclassified = []

	for voucher in vouchers.values():
		column, qty = get_column_and_qty(voucher)
		if not column:
			if voucher.net_qty < 0:
				unclassified.append(voucher)
			continue

		if voucher.posting_date < from_date:
			opening += qty if column in RECEIPTS else -qty
		else:
			movements[voucher.posting_date.replace(day=1)][column] += qty

	return opening, movements, unclassified


def get_column_and_qty(voucher):
	"""Column the voucher belongs to, with the quantity to show (issues as positive figures)."""
	if voucher.paddy_movement in ISSUE_COLUMNS:
		return ISSUE_COLUMNS[voucher.paddy_movement], voucher.out_qty

	receipt_column = RECEIPT_COLUMNS.get(voucher.paddy_source, OTHER_RECEIPT_COLUMN)
	if voucher.voucher_type == "Purchase Receipt":
		# A purchase return reduces the receipts of its source.
		return receipt_column, voucher.net_qty

	if voucher.net_qty > 0:
		return receipt_column, voucher.net_qty

	return None, 0.0


def get_months(from_date, to_date):
	months, month = [], getdate(from_date).replace(day=1)
	while month <= getdate(to_date):
		months.append(month)
		month = getdate(add_months(month, 1))
	return months


def build_rows(months, opening, movements):
	"""One row per month (zero rows included), then the Total row."""
	rows = []
	balance = flt(opening, PRECISION)

	for month in months:
		month_movements = movements.get(month) or {}
		row = {"month": month.strftime("%b-%y"), "ob": balance}
		for column in RECEIPTS + ISSUES:
			row[column] = flt(month_movements.get(column), PRECISION)

		set_totals(row)
		balance = row["cb"]
		rows.append(row)

	rows.append(get_total_row(rows))
	return rows


def set_totals(row):
	row["total_paddy"] = flt(row["ob"] + sum(row[column] for column in RECEIPTS), PRECISION)
	row["total"] = flt(sum(row[column] for column in ISSUES), PRECISION)
	row["cb"] = flt(row["total_paddy"] - row["total"], PRECISION)


def get_total_row(month_rows):
	"""OB of the first month, period sums of receipts and issues, CB of the last month."""
	total_row = {"month": _("Total"), "ob": month_rows[0]["ob"], "bold": 1}
	for column in RECEIPTS + ISSUES:
		total_row[column] = flt(sum(row[column] for row in month_rows), PRECISION)

	set_totals(total_row)
	total_row["cb"] = month_rows[-1]["cb"]
	return total_row


def get_message(ledger_rows, unclassified):
	messages = []

	items = sorted({row.item_code for row in ledger_rows})
	if len(items) > 1:
		messages.append(
			_("Figures include {0} items ({1}). Select a Paddy Item to see one item only.").format(
				len(items), ", ".join(items[:5])
			)
		)

	uoms = sorted({row.stock_uom for row in ledger_rows if row.stock_uom})
	if len(uoms) > 1:
		messages.append(
			_("These items use more than one stock UOM ({0}). Figures are added as they are.").format(
				", ".join(uoms)
			)
		)

	if unclassified:
		qty = flt(sum(-voucher.net_qty for voucher in unclassified), PRECISION)
		names = ", ".join(voucher.voucher_no for voucher in unclassified[:5])
		messages.append(
			_(
				"{0} paddy left through {1} stock entries whose type has no Paddy Movement ({2}). "
				"It is not in this statement, so CB can differ from the actual stock."
			).format(qty, len(unclassified), names)
		)

	return "<br>".join(messages) or None
