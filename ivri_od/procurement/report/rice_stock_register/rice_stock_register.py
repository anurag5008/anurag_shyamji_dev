# Copyright (c) 2026, Profezzo and contributors
"""Rice Stock Register: one row per day of CMR (Custom Milled Rice) with O.B., receipt from milling,
normal rice delivery to FCI / RRC, progressive totals and C.B., in Quintal (4 decimals).

Same filters as Paddy Stock Register (shared: ivri_od/procurement/stock_register.py): Mill, KMS Year,
Season, District (blank = all districts), From / To Date. "Prog." columns count from the season Start Date.

Data sources (all of the Mill, KMS Year, Season and District):
- Receipt from Milling: Paddy Stock Register's "Issue for Milling" of the same day (PVR "Paddy Milled
  during the week" spread over the week's days) x Rice Percentage for FCI (CMR %) of Rice Delivery
  Setup for the mill's Type (Raw / Boiled) in Mill Master.
- Normal Rice Delivery - FCI: DCRO "DC Transit Challan" Net Weight (after moisture cut) by Accepted Date.
- Normal Rice Delivery - RRC: SCMS "Lot Search" Qty by Receipt Date.
  A delivery row's District and Season are those of its DC in DCRO "View DC" (as in the Verification
  Report); a Lot Search row with its own District uses that District. Rejected / cancelled rows,
  rows without a date and rows whose DC is not in View DC are not counted (listed as warnings).
- O.B. = previous day's C.B. (season opening 0). Total Stock = O.B. + Receipt from Milling.
  Prog. Receipt = previous day's Prog. Receipt + Receipt from Milling.
  Total Prog = Prog. Delivery FCI + Prog. Delivery RRC. C.B. = Prog. Receipt - Total Prog.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, formatdate

from ivri_od.procurement import stock_register
from ivri_od.procurement.doctype.miller_verification_report.miller_verification_report import _Figures
from ivri_od.procurement.portal_sync import _match_key
from ivri_od.procurement.report.dc_track.dc_track import _dc_no
from ivri_od.procurement.report.paddy_stock_register.paddy_stock_register import get_issue_for_milling
from ivri_od.procurement.report.rice_stock_report.rice_stock_report import (
	FCI_DC_NO,
	FCI_SECTION,
	RRC_DC_NO,
	RRC_DISTRICT,
	RRC_SECTION,
	_rows,
	_skipped,
	fci_delivery,
	get_rice_percentage,
	rrc_delivery,
)
from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import season_master_year

PRECISION = 4

# Movement kinds: get_movements() returns (date, kind, qty) with one of these kinds.
RECEIPT_FROM_MILLING = "receipt_from_milling"
DELIVERY_FCI = "delivery_fci"  # Normal rice delivery to FCI
DELIVERY_RRC = "delivery_rrc"  # Normal rice delivery to RRC

RECEIPTS = (RECEIPT_FROM_MILLING,)
DELIVERIES = (DELIVERY_FCI, DELIVERY_RRC)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	season = stock_register.validate_filters(filters, district_required=False)

	notes = []
	movements = get_movements(filters, filters.to_date, notes)
	data = build_rows(season.start_date, filters.from_date, filters.to_date, 0, movements)

	title = stock_register.get_title("RICE STOCK REGISTER", filters)
	if data:
		data[0].register_title = title  # heading of the print layout (.html)
	return get_columns(), data, stock_register.get_message(title, data, notes + negative_cb_warnings(data))


def get_columns():
	"""Column order here is also the Excel / CSV order."""
	columns = [{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100}]
	for label, fieldname, width in (
		(_("O.B. (CMR)"), "ob", 120),
		(_("Receipt from Milling"), "receipt_from_milling", 140),
		(_("Total Stock (CMR)"), "total_stock", 140),
		(_("Prog. Receipt (CMR)"), "prog_receipt", 140),
		(_("Normal Rice Delivery - FCI"), "delivery_fci", 170),
		(_("Normal Rice Delivery - RRC"), "delivery_rrc", 170),
		(_("Prog. Delivery - FCI"), "prog_delivery_fci", 140),
		(_("Prog. Delivery - RRC"), "prog_delivery_rrc", 140),
		(_("Total Prog FCI+RRC"), "total_prog_delivery", 150),
		(_("C.B. (CMR)"), "cb", 120),
	):
		columns.append(
			{"label": label, "fieldname": fieldname, "fieldtype": "Float", "precision": PRECISION, "width": width}
		)
	return columns


def get_movements(filters, to_date, notes) -> list[tuple]:
	"""CMR movements of the mill up to ``to_date`` as (date, kind, qty); warnings go into ``notes``."""
	return get_receipts_from_milling(filters, to_date) + get_deliveries(filters, to_date, notes)


def get_receipts_from_milling(filters, to_date):
	"""(date, RECEIPT_FROM_MILLING, rice qty): the Paddy Stock Register's Issue for Milling of each day
	x CMR % of Rice Delivery Setup, so both registers move together day by day."""
	percentage = get_rice_percentage(filters.mill)  # stops with a message when not set up
	return [
		(date, RECEIPT_FROM_MILLING, flt(qty) * percentage / 100)
		for date, _kind, qty in get_issue_for_milling(filters, to_date)
	]


def get_deliveries(filters, to_date, notes):
	"""(date, DELIVERY_FCI / DELIVERY_RRC, qty) of the KMS Year whose DC is of the Season and District
	(every District when blank)."""
	year = int(season_master_year(filters.kms_year))
	dcs = _Figures(filters.mill, year, [], None, to_date).view_dcs()  # {DC No.: District, Season, ...}
	out = []
	for kind, site, section, read_row, dc_column, district_column, date_label in (
		(DELIVERY_FCI, "DCRO", FCI_SECTION, fci_delivery, FCI_DC_NO, None, _("Accepted Date")),
		(DELIVERY_RRC, "SCMS", RRC_SECTION, rrc_delivery, RRC_DC_NO, RRC_DISTRICT, _("Receipt Date")),
	):
		without_dc = without_date = 0
		for cells in _rows(site, section, filters.mill, year):
			if _skipped(cells):
				continue
			dc = dcs.get(_dc_no(cells.get(dc_column)))
			district = (district_column and (cells.get(district_column) or "").strip()) or (dc and dc.district)
			if not dc or (filters.district and not district):
				without_dc += 1
				continue
			if (dc.season or "").strip().casefold() != filters.season.casefold():
				continue
			if filters.district and _match_key(district) != _match_key(filters.district):
				continue
			when, _depot, qty = read_row(cells)
			if when is None:
				without_date += 1
			elif when <= to_date:
				out.append((when, kind, qty))
		if without_dc:
			notes.append(
				_("{0} {1} rows are not counted: their DC is not in View DC from DCRO or has no District.").format(
					without_dc, section
				)
			)
		if without_date:
			notes.append(_("{0} {1} rows are not counted: they have no {2} yet.").format(without_date, section, date_label))
	return out


def build_rows(season_start, from_date, to_date, season_opening, movements):
	"""Report rows from the shared day-wise loop. Every number shows 0.0000, never blank."""
	rows = []
	for e in stock_register.day_rows(
		season_start, from_date, to_date, season_opening, movements, RECEIPTS, DELIVERIES
	):
		prog = e.prog
		rows.append(
			frappe._dict(
				date=e.date,
				ob=rnd(e.ob),
				receipt_from_milling=rnd(e.day.get(RECEIPT_FROM_MILLING)),
				total_stock=rnd(e.total_stock),
				prog_receipt=rnd(prog.get(RECEIPT_FROM_MILLING)),
				delivery_fci=rnd(e.day.get(DELIVERY_FCI)),
				delivery_rrc=rnd(e.day.get(DELIVERY_RRC)),
				prog_delivery_fci=rnd(prog.get(DELIVERY_FCI)),
				prog_delivery_rrc=rnd(prog.get(DELIVERY_RRC)),
				total_prog_delivery=rnd(flt(prog.get(DELIVERY_FCI)) + flt(prog.get(DELIVERY_RRC))),
				cb=rnd(e.cb),
				mismatch=e.mismatch,
			)
		)
	return rows


def negative_cb_warnings(rows):
	"""Warning when C.B. goes below zero on any day."""
	negative = [row for row in rows if row.cb < 0]
	if not negative:
		return []
	return [
		_("C.B. is negative on {0} day(s), first on {1}.").format(len(negative), formatdate(negative[0].date))
	]


def rnd(value):
	return flt(value, PRECISION)
