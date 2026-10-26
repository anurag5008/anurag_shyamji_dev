# Copyright (c) 2026, Profezzo and contributors
"""Stock Account for Paddy: monthly OB, receipts, milling issue, driage and CB for Civil Supplies.

PACs: government GRN Notes of the mill, KMS Year (Kharif and Rabi of one Season Master year,
shown as "25-26" for year 2025) and PPC district.
Each transit pass counts
its TP quantity once fulfilled, else what was received (effective_tp_quantity_for_pass),
spread over the months of its GRNs in receipt order.
Issue for Milling: paddy released for milling in the DCRO "Paddy Release" rows of the mill.
WSHGs, Other Rect and Driage have no source yet and stay 0."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_first_day, get_last_day, getdate

from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.portal_report import _load, _sum_of
from ivri_od.procurement.ppc_pass_metrics import effective_tp_quantity_for_pass
from ivri_od.procurement.report.paddy_release_from_dcro.paddy_release_from_dcro import (
	BALANCE as DCRO_BALANCE,
	DATE_COLUMN as DCRO_DATE_COLUMN,
	SECTION as DCRO_SECTION,
)
from ivri_od.procurement.transit_pass_resolve import mill_id_from_transit_pass, resolve_ppc_master_name

RECEIPTS = ("pacs", "wshgs", "other_rect")
ISSUES = ("issue_for_milling", "driage")
PRECISION = 2
# Same order as the TP fulfillment of GRN Notes (grn_tp_fulfillment.py).
GRN_ORDER = "receipt_datetime asc, receipt_date asc, receipt_time asc, creation asc"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = validate_filters(filters)

	seasons = get_kms_seasons(filters.kms_year)
	grns, skipped_grns = get_grns(filters, seasons, to_date)
	releases = get_dcro_releases(filters, seasons, to_date)
	opening, movements = classify(grn_receipts(grns, get_tp_quantities(grns)) + releases, from_date)
	data = build_rows(get_months(from_date, to_date), opening, movements)

	return get_columns(), data, get_message(skipped_grns, filters)


def validate_filters(filters):
	for fieldname, label in (
		("mill", _("Mill Name")),
		("kms_year", _("KMS Year")),
		("paddy_account", _("District")),
		("from_month", _("From Month")),
		("to_month", _("To Month")),
	):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is mandatory").format(label))

	# The mill's company is printed in the heading.
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


@frappe.whitelist()
def get_kms_years():
	"""KMS Years of Season Master, newest first: year 2025 (Kharif 2025, Rabi 2025) is "25-26"."""
	years = {cint(year) for year in frappe.get_all("Season Master", pluck="year") if cint(year)}
	return [kms_year_label(year) for year in sorted(years, reverse=True)]


def kms_year_label(year):
	return f"{year % 100:02d}-{(year + 1) % 100:02d}"


def season_master_year(kms_year):
	"""Season Master year of a KMS Year: "25-26" -> "2025"."""
	match = re.fullmatch(r"(\d{2})-(\d{2})", (kms_year or "").strip())
	if not match or (int(match.group(1)) + 1) % 100 != int(match.group(2)):
		frappe.throw(_("KMS Year must look like 25-26"))
	return str(2000 + int(match.group(1)))


def get_kms_seasons(kms_year):
	"""Season Masters (Kharif and Rabi) of the KMS Year, e.g. 25-26 -> Kharif 2025, Rabi 2025."""
	seasons = frappe.get_all("Season Master", filters={"year": season_master_year(kms_year)}, pluck="name")
	if not seasons:
		frappe.throw(_("No Season Master is in KMS Year {0}").format(kms_year))
	return seasons


def get_grns(filters, seasons, to_date):
	"""Government GRN Notes of the mill and KMS Year up to To Month, with the PPC in the District.

	Returns (grns, skipped): skipped are GRNs of the mill and year whose PPC has no District.
	"""
	rows = frappe.get_all(
		"GRN Note",
		filters={
			"is_local_procurement": 0,
			"docstatus": ["<", 2],
			"pass_unique_key": ["like", f"{filters.mill}-%"],
			"receipt_date": ["<=", to_date],
		},
		fields=[
			"name",
			"pass_unique_key",
			"mill_name",
			"cmr_season",
			"ppc",
			"tp_quantity",
			"net_weight",
			"receipt_date",
		],
		order_by=GRN_ORDER,
		limit_page_length=0,
	)

	season_of, district_of = {}, {}
	grns, skipped = [], []
	for row in rows:
		mill = mill_id_from_transit_pass({"pass_unique_key": row.pass_unique_key, "miller": row.mill_name})
		if mill != filters.mill:
			continue

		season_text = row.cmr_season or season_code_from_pass_key(row.pass_unique_key)
		if season_text not in season_of:
			season_of[season_text] = resolve_season_master_name(season_text)
		if season_of[season_text] not in seasons:
			continue

		if row.ppc not in district_of:
			ppc = resolve_ppc_master_name(row.ppc)
			district_of[row.ppc] = ppc and frappe.db.get_value("PPC Master", ppc, "district")
		if not district_of[row.ppc]:
			skipped.append(row)
		elif district_of[row.ppc] == filters.paddy_account:
			grns.append(row)

	return grns, skipped


def season_code_from_pass_key(pass_unique_key):
	"""Season code of a pass key: "M051007-BAKTI(S1050104)-K25-TP45" -> "K25"."""
	parts = (pass_unique_key or "").rsplit("-", 2)
	return parts[1] if len(parts) == 3 else ""


def get_tp_quantities(grns):
	"""{pass key: TP quantity}: the largest TP quantity on its GRNs, else the PPAS Transit Pass quantity."""
	tp_quantities = defaultdict(float)
	for grn in grns:
		tp_quantities[grn.pass_unique_key] = max(tp_quantities[grn.pass_unique_key], flt(grn.tp_quantity))

	missing = [key for key, qty in tp_quantities.items() if not qty]
	if missing:
		for tp in frappe.get_all(
			"PPAS Transit Pass",
			filters={"pass_unique_key": ["in", missing]},
			fields=["pass_unique_key", "quantity"],
		):
			tp_quantities[tp.pass_unique_key] = flt(tp.quantity)

	return tp_quantities


def grn_receipts(grns, tp_quantities):
	"""PACs quantity of each GRN as (date, "pacs", qty).

	Per pass, in receipt order: what the pass counts after this GRN minus what it counted before,
	so a fulfilled TP counts its TP quantity once and a short TP counts what was received.
	"""
	received_so_far = defaultdict(float)
	receipts = []
	for grn in grns:
		key = grn.pass_unique_key
		before = effective_tp_quantity_for_pass(received_so_far[key], tp_quantities[key])
		received_so_far[key] += flt(grn.net_weight)
		after = effective_tp_quantity_for_pass(received_so_far[key], tp_quantities[key])
		receipts.append((getdate(grn.receipt_date), "pacs", after - before))
	return receipts


def get_dcro_releases(filters, seasons, to_date):
	"""Paddy released for milling as (date, "issue_for_milling", qty), from the DCRO Paddy Release
	rows of the mill (own and other district added up, rejected or cancelled orders left out).
	Rows before the KMS Year's first start date, when it is set, belong to an earlier year."""
	starts = frappe.get_all("Season Master", filters={"name": ["in", seasons]}, pluck="start_date")
	season_start = min((start for start in starts if start), default=None)
	skip_status = [word.lower() for word in DCRO_BALANCE["skip_status"]]

	releases = []
	for record in frappe.get_all(
		"Portal Record",
		filters={"site": "DCRO", "section": DCRO_SECTION, "mill_id": filters.mill},
		fields=["row_data"],
		limit_page_length=0,
	):
		release = dcro_release(_load(record.row_data), skip_status)
		if not release:
			continue
		if release[0] > to_date or (season_start and release[0] < getdate(season_start)):
			continue
		releases.append(release)
	return releases


def dcro_release(cells, skip_status):
	"""(date, "issue_for_milling", qty) of one DCRO row, or None without a date or for a rejected order."""
	status = " ".join(value for header, value in cells.items() if "status" in header.lower()).lower()
	if any(word in status for word in skip_status):
		return None
	release_date = parse_portal_date(cells.get(DCRO_DATE_COLUMN))
	if not release_date:
		return None
	return release_date, "issue_for_milling", flt(_sum_of(cells, DCRO_BALANCE["released"]))


def parse_portal_date(value):
	"""dd-mm-yyyy or dd/mm/yyyy as on the portal."""
	text = (value or "").strip()
	for date_format in ("%d-%m-%Y", "%d/%m/%Y"):
		try:
			return datetime.strptime(text, date_format).date()
		except ValueError:
			continue
	return None


def classify(movements, from_date):
	"""Return (opening balance, {month: {column: qty}}) from (date, column, qty) movements."""
	opening = 0.0
	by_month = defaultdict(lambda: defaultdict(float))
	for movement_date, column, qty in movements:
		if movement_date < from_date:
			opening += qty if column in RECEIPTS else -qty
		else:
			by_month[movement_date.replace(day=1)][column] += qty
	return opening, by_month


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


def get_message(skipped_grns, filters):
	if not skipped_grns:
		return None
	ppcs = sorted({grn.ppc for grn in skipped_grns if grn.ppc})
	return _(
		"{0} GRN Notes of mill {1} are not counted because their PPC has no District in PPC Master: {2}"
	).format(len(skipped_grns), filters.mill, ", ".join(ppcs[:10]) or _("PPC not set"))
