# Copyright (c) 2026, Profezzo and contributors
"""Shared logic of the day-wise stock registers (Paddy Stock Register, Rice Stock Register).

- Filters: Mill Name (Mill Master), KMS Year ("25-26"), Season (Kharif / Rabi), District
  (District Master, printed as "AC - <District>"), From / To Date.
- Season from Season Master (KMS Year + Kharif / Rabi). Start / End Date are optional: the data
  is already of that KMS Year and season, so without a Start Date "Prog." totals count every
  movement up to the day; with one, they count from it.
- day_rows(): one entry per day with O.B., the day's movements, progressive totals and C.B.
  Each report turns these into its own columns.
"""

from __future__ import annotations

import datetime
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, formatdate, getdate

from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	season_master_year,
)

SEASONS = ("Kharif", "Rabi")


ALL_DISTRICTS = "All Districts"


def validate_filters(filters, district_required=True):
	"""Check the common filters, set filters.company and filters.ac (the District filter) and return
	the Season Master (name, start_date, end_date).

	With ``district_required=False`` the District may be blank: filters.district stays empty
	(= all districts) and filters.ac is "All Districts"."""
	mandatory = [
		("mill", _("Mill Name")),
		("kms_year", _("KMS Year")),
		("season", _("Season")),
		("district", _("District")),
		("from_date", _("From Date")),
		("to_date", _("To Date")),
	]
	if not district_required:
		mandatory = [m for m in mandatory if m[0] != "district"]
	for fieldname, label in mandatory:
		if not filters.get(fieldname):
			frappe.throw(_("{0} is mandatory").format(label))

	if filters.season not in SEASONS:
		frappe.throw(_("Season must be Kharif or Rabi"))

	# The mill's company and the District account (AC) are printed in the heading.
	filters.company = frappe.db.get_value("Mill Master", filters.mill, "company")
	if not filters.company:
		frappe.throw(_("Set the Company in Mill Master {0}").format(filters.mill))
	if filters.get("district"):
		if not frappe.db.exists("District Master", filters.district):
			frappe.throw(_("District {0} not found").format(filters.district))
		filters.ac = filters.district
	else:
		filters.district = None
		filters.ac = ALL_DISTRICTS

	season = get_season(filters.kms_year, filters.season)

	filters.from_date = getdate(filters.from_date)
	filters.to_date = getdate(filters.to_date)
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be before To Date"))
	if season.start_date and filters.from_date < season.start_date:
		frappe.throw(
			_("From Date {0} is before the start of {1} ({2}).").format(
				formatdate(filters.from_date), season.name, formatdate(season.start_date)
			)
		)
	if season.end_date and filters.to_date > season.end_date:
		frappe.throw(
			_("To Date {0} is after the end of {1} ({2}).").format(
				formatdate(filters.to_date), season.name, formatdate(season.end_date)
			)
		)
	return season


def get_season(kms_year, crop_season):
	"""Season Master of the KMS Year and season, e.g. 25-26 + Kharif -> "Kharif 2025"."""
	season = frappe.db.get_value(
		"Season Master",
		{"year": season_master_year(kms_year), "crop_season": crop_season},
		["name", "start_date", "end_date"],
		as_dict=True,
	)
	if not season:
		frappe.throw(_("No Season Master for {0} in KMS Year {1}").format(crop_season, kms_year))
	# Start Date is optional (None = no lower limit): the data is already filtered by KMS Year and season.
	season.start_date = getdate(season.start_date) if season.start_date else None
	season.end_date = getdate(season.end_date) if season.end_date else None
	return season


def get_title(register, filters):
	"""e.g. "PADDY STOCK REGISTER KMS 2025-26 M/s <Company> , AC - <AC>, Kharif"."""
	kms = f"20{filters.kms_year}" if filters.kms_year else ""
	return f"{register} KMS {kms} M/s {filters.company} , AC - {filters.ac}, {filters.season}"


def day_rows(season_start, from_date, to_date, season_opening, movements, receipts, disposals, others=()):
	"""One entry per day From Date -> To Date (days without movement included).

	movements: (date, kind, qty). ``receipts`` add to stock, ``disposals`` reduce it, ``others``
	(e.g. Release Order) are only counted. Movements before the season start or of other kinds are
	ignored; those before From Date go into the first O.B. and the progressive totals.

	Each entry: date, ob, day ({kind: qty}, only kinds with an entry that day), prog ({kind: qty}
	from season start up to and including the day), total_stock, cb, mismatch (1 when
	C.B. != season opening + progressive receipts - progressive disposals).
	"""
	# No season start (Season Master without Start Date): count every movement before From Date.
	season_start = getdate(season_start) if season_start else datetime.date.min
	from_date, to_date = getdate(from_date), getdate(to_date)
	kinds = (*receipts, *disposals, *others)

	by_day = defaultdict(lambda: defaultdict(float))
	prog = defaultdict(float)
	for date, kind, qty in movements:
		date = getdate(date)
		if kind not in kinds or date < season_start or date > to_date:
			continue
		if date < from_date:
			prog[kind] += flt(qty)
		else:
			by_day[date][kind] += flt(qty)

	def total(qty_by_kind, of_kinds):
		return sum(flt(qty_by_kind.get(kind, 0)) for kind in of_kinds)

	ob = flt(season_opening) + total(prog, receipts) - total(prog, disposals)
	entries = []
	for i in range(date_diff(to_date, from_date) + 1):
		date = add_days(from_date, i)
		day = dict(by_day.get(date, {}))
		for kind, qty in day.items():
			prog[kind] += qty

		total_stock = ob + total(day, receipts)
		cb = total_stock - total(day, disposals)
		expected = flt(season_opening) + total(prog, receipts) - total(prog, disposals)
		entries.append(
			frappe._dict(
				date=date,
				ob=ob,
				day=day,
				prog=dict(prog),
				total_stock=total_stock,
				cb=cb,
				mismatch=int(abs(expected - cb) > 0.00005),
			)
		)
		ob = cb  # next day's O.B. is this day's C.B.
	return entries


def get_message(title, rows, extra=()):
	"""Title line on screen, then warnings (red)."""
	parts = [f"<div style='font-weight:bold;text-align:center'>{frappe.utils.escape_html(title)}</div>"]
	mismatches = sum(1 for row in rows if row.mismatch)
	if mismatches:
		parts.append(
			_("{0} day(s) where C.B. does not match season opening + Prog. Receipt - Prog. Disposal.").format(
				mismatches
			)
		)
	parts.extend(extra)
	return parts[0] + "".join(f"<div style='color:red'>{p}</div>" for p in parts[1:])
