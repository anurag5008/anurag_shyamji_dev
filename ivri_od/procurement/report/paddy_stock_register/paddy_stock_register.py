# Copyright (c) 2026, Profezzo and contributors
"""Paddy Stock Register: one row per day with OB, receipts, progressive receipts, release order,
issue for milling, total disposal and CB, in Quintal (2 decimals).

Filters, season dates and the day-wise loop are shared with Rice Stock Register
(ivri_od/procurement/stock_register.py). "Prog." columns count from the season Start Date.
All data is of the Mill, the District (filter) and the Season (Kharif / Rabi of the KMS Year).
District blank = all districts (every Transit Pass, DCRO district column and PVR row of the mill).

Data sources:
- Receipt PACS: TP quantity of the mill's PPAS Transit Passes of the season whose PPC is in the
  District in PPC Master, by Transit Pass Date. Receipt SHG: the same for PPCs ticked "Is WSHG"
  (they are not in PACS).
- Release Order: DCRO "Paddy Release" rows of the mill, KMS Year and Season: the District's
  "Paddy Released for Milling", by Date of Requistion (rejected / cancelled orders left out).
  Release Order is only counted; it does not change O.B. / C.B.
- Issue for Milling: "Paddy Milled during the week" of the District and Season rows of the mill's
  submitted PVRs (Miller Verification Report) of the KMS Year, spread over the days of the week
  (see split_milling): Last Verification Date up to the day before the Present Verification Date.
  The first PVR (no Last Verification Date) puts it all on the day before its Present Verification Date.
- O.B. = previous day's C.B. (season opening 0). C.B. = Prog. Receipt (Total) - Prog. Issue for Milling.
"""

from __future__ import annotations

import math
import random

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, getdate

from ivri_od.procurement import stock_register
from ivri_od.procurement.doctype.milling_capacity_master.milling_capacity_master import (
	get_min_daily_milling,
)
from ivri_od.procurement.dcro_paddy_release import SEASON_COLUMN as DCRO_SEASON_COLUMN
from ivri_od.procurement.dcro_paddy_release import district_names
from ivri_od.procurement.portal_report import _load
from ivri_od.procurement.report.paddy_release_from_dcro.paddy_release_from_dcro import (
	BALANCE as DCRO_BALANCE,
	SECTION as DCRO_SECTION,
)
from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	DCRO_KMS_COLUMN,
	dcro_kms_year,
	dcro_release,
	mill_transit_passes,
	season_master_year,
)

PRECISION = 2

# Movement kinds: get_movements() returns (date, kind, qty) with one of these kinds.
RECEIPT_PACS = "receipt_pacs"
RECEIPT_SHG = "receipt_shg"
RELEASE_ORDER = "release_order"  # not a stock movement: never changes OB / CB
ISSUE_FOR_MILLING = "issue_for_milling"
# Other disposal kinds (e.g. "driage") may be added here later; they reduce CB and add to Total Disposal.
OTHER_DISPOSALS: tuple[str, ...] = ()

RECEIPTS = (RECEIPT_PACS, RECEIPT_SHG)
DISPOSALS = (ISSUE_FOR_MILLING, *OTHER_DISPOSALS)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	season = stock_register.validate_filters(filters, district_required=False)

	passes, skipped = get_transit_passes(filters, season)
	movements = (
		tp_receipts(passes)
		+ get_release_orders(filters, filters.to_date)
		+ get_issue_for_milling(filters, filters.to_date)
	)
	data = build_rows(season.start_date, filters.from_date, filters.to_date, 0, movements)

	title = stock_register.get_title("PADDY STOCK REGISTER", filters)
	if data:
		data[0].register_title = title  # heading of the print layout (.html)
	extra = []
	if skipped:
		extra.append(
			_("{0} Transit Passes of mill {1} are not counted: their PPC is not in PPC Master or has no District.").format(
				len(skipped), filters.mill
			)
		)
	return get_columns(), data, stock_register.get_message(title, data, extra)


def get_columns():
	"""Column order here is also the Excel / CSV order."""
	columns = [{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100}]
	for label, fieldname, width in (
		(_("O.B."), "ob", 110),
		(_("Receipt - PACS"), "receipt_pacs", 120),
		(_("Receipt - SHG"), "receipt_shg", 120),
		(_("Total Stock"), "total_stock", 120),
		(_("Prog. Receipt - PACS"), "prog_receipt_pacs", 150),
		(_("Prog. Receipt - SHG"), "prog_receipt_shg", 150),
		(_("Total of Prog. Receipt"), "prog_receipt_total", 150),
		(_("Release Order"), "release_order", 120),
		(_("Prog. Release Order"), "prog_release_order", 140),
		(_("Issue for Milling"), "issue_for_milling", 130),
		(_("Prog. Issue for Milling"), "prog_issue_for_milling", 150),
		(_("Total Disposal"), "total_disposal", 120),
		(_("C.B."), "cb", 110),
	):
		columns.append(
			{"label": label, "fieldname": fieldname, "fieldtype": "Float", "precision": PRECISION, "width": width}
		)
	return columns


# ---------------------------------------------------------------- receipts (Transit Passes)


def get_transit_passes(filters, season):
	"""(passes, skipped): Transit Passes of the mill and Season up to To Date with the PPC in the
	District; skipped = passes of the mill whose PPC is not in PPC Master or has no District.
	Without a District: every pass of the mill and Season, nothing skipped."""
	passes, skipped = [], []
	for row in mill_transit_passes(filters.mill, [season.name], filters.to_date):
		if not filters.district:
			passes.append(row)
		elif not row.district:
			skipped.append(row)
		elif row.district == filters.district:
			passes.append(row)
	return passes, skipped


def tp_receipts(passes):
	"""(Transit Pass Date, RECEIPT_SHG when the PPC is ticked Is WSHG else RECEIPT_PACS, TP quantity)."""
	return [
		(getdate(tp.transit_pass_date), RECEIPT_SHG if tp.get("is_wshg") else RECEIPT_PACS, flt(tp.quantity))
		for tp in passes
		if tp.transit_pass_date
	]


# ---------------------------------------------------------------- release order (DCRO)


def get_release_orders(filters, to_date):
	"""(Date of Requistion, RELEASE_ORDER, qty) of the DCRO Paddy Release rows of the mill, KMS Year
	and Season: only the District's Paddy Released (all districts' when no District).
	Rows without KMS Year / Season are not counted."""
	year = cint(season_master_year(filters.kms_year))
	skip_status = [word.lower() for word in DCRO_BALANCE["skip_status"]]
	own_district = frappe.db.get_value("Mill Master", filters.mill, "district")
	districts = district_names()

	releases = []
	for record in frappe.get_all(
		"Portal Record",
		filters={"site": "DCRO", "section": DCRO_SECTION, "mill_id": filters.mill},
		fields=["row_data"],
		limit_page_length=0,
	):
		cells = _load(record.row_data)
		if dcro_kms_year(cells.get(DCRO_KMS_COLUMN)) != year:
			continue
		if (cells.get(DCRO_SEASON_COLUMN) or "").strip().casefold() != filters.season.casefold():
			continue
		release = dcro_release(cells, skip_status, filters.district, own_district, districts)
		if release and release[0] <= to_date and release[2]:
			releases.append((release[0], RELEASE_ORDER, release[2]))
	return releases


# ---------------------------------------------------------------- issue for milling (PVR)


def get_issue_for_milling(filters, to_date):
	"""(date, ISSUE_FOR_MILLING, qty): "Paddy Milled during the week" of the District (all
	districts when blank) and Season (both seasons when blank) rows of the mill's submitted PVRs
	of the KMS Year, spread over the week's days. Each district / season row is split on its own,
	so the totals are the same however the rows are filtered. Also used by Stock Account for Paddy."""
	year = cint(season_master_year(filters.kms_year))
	mill_type = frappe.db.get_value("Mill Master", filters.mill, "type")
	minimum = get_min_daily_milling(mill_type)

	pvr = frappe.qb.DocType("Miller Verification Report")
	row = frappe.qb.DocType("Miller Verification Agency")
	condition = (
		(pvr.docstatus == 1)
		& (pvr.miller_code == filters.mill)
		& (row.paddy_milled_week > 0)
		& (pvr.present_verification_date.isnotnull())
	)
	if filters.get("season"):
		condition &= row.season == filters.season
	if filters.district:
		condition &= row.district == filters.district
	records = (
		frappe.qb.from_(pvr)
		.join(row)
		.on((row.parent == pvr.name) & (row.parenttype == "Miller Verification Report"))
		.select(
			pvr.name,
			pvr.kms,
			pvr.last_verification_date,
			pvr.present_verification_date,
			row.district,
			row.season,
			row.paddy_milled_week,
		)
		.where(condition)
		.orderby(pvr.present_verification_date)
		.run(as_dict=True)
	)

	movements = []
	for rec in records:
		if dcro_kms_year(rec.kms) != year:
			continue
		days = pvr_days(rec.last_verification_date, rec.present_verification_date)
		seed = f"{rec.name}|{rec.district}|{rec.season}"  # same split every time the report runs
		for date, qty in split_milling(flt(rec.paddy_milled_week), days, minimum, seed):
			if date <= to_date:
				movements.append((date, ISSUE_FOR_MILLING, qty))
	return movements


def pvr_days(last_date, present_date):
	"""Days of one PVR week: the milling happened before the Present Verification Date.

	- Last Verification Date up to the day before the Present Verification Date
	  (e.g. 06-05 -> 08-05 gives 06-05 and 07-05).
	- First PVR (no Last Verification Date), or dates not in order: only the day before the
	  Present Verification Date (e.g. present 06-05 gives 05-05).
	Weeks do not overlap, so on the day before each Present Verification Date the register's
	Prog. Issue for Milling equals the PVR's "Prog. Paddy Milled"."""
	present_date = getdate(present_date)
	day_before = add_days(present_date, -1)
	if not last_date or getdate(last_date) >= present_date:
		return [day_before]
	last_date = getdate(last_date)
	return [add_days(last_date, i) for i in range(date_diff(present_date, last_date))]


def split_milling(total, days, minimum, seed):
	"""Spread ``total`` over ``days`` at random as [(date, qty)], adding up exactly to ``total``.

	Each day with milling gets at least ``minimum``, so only total // minimum days can have milling
	(the others get nothing). If ``total`` is below ``minimum`` it all goes on one day.
	Each day gets a whole number; only when ``total`` itself has decimals does the last day keep them.
	The split is random but fixed by ``seed`` (the PVR), so the report shows the same figures every time.
	"""
	total = flt(total, PRECISION)
	if total <= 0 or not days:
		return []
	rng = random.Random(seed)
	count = max(1, min(len(days), int(total // minimum) if minimum > 0 else len(days)))
	chosen = sorted(rng.sample(list(days), count))
	if count == 1:
		return [(chosen[0], total)]

	extra = total - count * minimum  # >= 0, spread at random over the chosen days
	weights = [rng.random() for _ in chosen]
	weight_total = sum(weights) or 1
	split, given = [], 0.0
	for i, date in enumerate(chosen):
		if i == count - 1:
			qty = flt(total - given, PRECISION)  # last day takes what is left (keeps any decimals)
		else:
			# Whole number, at least the minimum; rounded down so the last day never drops below it.
			qty = float(math.ceil(minimum) + math.floor(extra * weights[i] / weight_total))
			given += qty
		split.append((date, qty))
	return split


# ---------------------------------------------------------------- rows


def build_rows(season_start, from_date, to_date, season_opening, movements):
	"""Report rows from the shared day-wise loop."""
	rows = []
	for e in stock_register.day_rows(
		season_start, from_date, to_date, season_opening, movements, RECEIPTS, DISPOSALS, (RELEASE_ORDER,)
	):
		prog = e.prog
		rows.append(
			frappe._dict(
				date=e.date,
				ob=rnd(e.ob),
				receipt_pacs=rnd(e.day.get(RECEIPT_PACS)),
				receipt_shg=rnd(e.day.get(RECEIPT_SHG)),
				total_stock=rnd(e.total_stock),
				prog_receipt_pacs=rnd(prog.get(RECEIPT_PACS)),
				prog_receipt_shg=rnd(prog.get(RECEIPT_SHG)),
				prog_receipt_total=rnd(sum(flt(prog.get(k)) for k in RECEIPTS)),
				# Blank (not 0.00) when there is no entry that day.
				release_order=rnd(e.day[RELEASE_ORDER]) if RELEASE_ORDER in e.day else None,
				prog_release_order=rnd(prog.get(RELEASE_ORDER)),
				issue_for_milling=rnd(e.day[ISSUE_FOR_MILLING]) if ISSUE_FOR_MILLING in e.day else None,
				prog_issue_for_milling=rnd(prog.get(ISSUE_FOR_MILLING)),
				total_disposal=rnd(sum(flt(prog.get(k)) for k in DISPOSALS)),
				cb=rnd(e.cb),
				mismatch=e.mismatch,
			)
		)
	return rows


def rnd(value):
	return flt(value, PRECISION)
