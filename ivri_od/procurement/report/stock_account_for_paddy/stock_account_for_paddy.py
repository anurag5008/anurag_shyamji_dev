# Copyright (c) 2026, Profezzo and contributors
"""Stock Account for Paddy: monthly OB, receipts, milling issue, driage and CB for Civil Supplies.

PACs: PPAS Transit Passes of the mill and KMS Year (Kharif and Rabi of one Season Master year,
shown as "25-26" for year 2025) whose PPC is assigned to the District in PPC Master: the TP
quantity, by Transit Pass Date month.
WSHGs: the same, for the Transit Passes whose PPC is ticked "Is WSHG" in PPC Master (they are
not in PACs).
Paddy Released: paddy released for milling in the DCRO "Paddy Release" rows of the mill and
KMS Year (the row's KMS Year, e.g. "2024-2025" for 24-25), by Date of Requistion month, of the District only (Own District columns when it is the mill's
District in Mill Master, else the Other District columns named with it; see dcro_paddy_release.py).
Only shown: it does not change OB / CB.
Issue for Milling: the Paddy Stock Register's Issue for Milling (PVR "Paddy Milled during the week"
spread over the days of each week) of the mill, District and KMS Year (Kharif and Rabi), by month.
Other Rect and Driage have no source yet and stay 0."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt, get_first_day, get_last_day, getdate

from ivri_od.procurement.dcro_paddy_release import district_names, released_by_district
from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.portal_report import _load, _sum_of
from ivri_od.procurement.report.paddy_release_from_dcro.paddy_release_from_dcro import (
	BALANCE as DCRO_BALANCE,
	DATE_COLUMN as DCRO_DATE_COLUMN,
	SECTION as DCRO_SECTION,
)
from ivri_od.procurement.transit_pass_resolve import mill_id_from_transit_pass, resolve_ppc_master_name

DCRO_KMS_COLUMN = "KMS Year"  # Page Filter Columns "KMS Year = #INTKMS"
RECEIPTS = ("pacs", "wshgs", "other_rect")
ISSUES = ("issue_for_milling", "driage")
PADDY_RELEASED = "paddy_released"
OTHERS = (PADDY_RELEASED,)  # only shown: not a stock movement, never changes OB / CB
PRECISION = 2


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = validate_filters(filters)

	if filters.kms_year not in get_kms_years(filters.mill):
		# No Transit Pass of the mill in the KMS Year: no statement.
		return get_columns(), [], _("Mill {0} has no Transit Pass data in KMS Year {1}.").format(
			filters.mill, filters.kms_year
		)

	seasons = get_kms_seasons(filters.kms_year)
	passes, skipped_passes = get_transit_passes(filters, seasons, to_date)
	releases = get_dcro_releases(filters, to_date)
	paddy_released = [(date, PADDY_RELEASED, qty) for date, _column, qty in releases]
	opening, movements = classify(
		tp_receipts(passes) + paddy_released + get_issue_for_milling(filters, to_date), from_date
	)
	data = build_rows(get_months(from_date, to_date), opening, movements)

	return get_columns(), data, get_message(skipped_passes, filters, releases)


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
		(_("Paddy Released"), "paddy_released", 140),
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
def get_kms_years(mill=None):
	"""KMS Years of Season Master, newest first: year 2025 (Kharif 2025, Rabi 2025) is "25-26".
	With ``mill``: only the years in which the mill has PPAS Transit Passes."""
	year_of = {row.name: cint(row.year) for row in frappe.get_all("Season Master", fields=["name", "year"])}
	years = {year for year in year_of.values() if year}
	if mill:
		years &= mill_tp_years(mill, year_of)
	return [kms_year_label(year) for year in sorted(years, reverse=True)]


def mill_tp_years(mill, year_of) -> set[int]:
	"""Season Master years of the mill's PPAS Transit Passes (season from the pass, else its key)."""
	rows = frappe.db.sql(
		"""
		SELECT season, miller, SUBSTRING_INDEX(pass_unique_key, '-', 1) AS key_mill,
			SUBSTRING_INDEX(SUBSTRING_INDEX(pass_unique_key, '-', -2), '-', 1) AS key_season
		FROM `tabPPAS Transit Pass`
		GROUP BY season, miller, key_mill, key_season
		""",
		as_dict=True,
	)
	years, season_of = set(), {}
	for row in rows:
		row_mill = mill_id_from_transit_pass(
			{"pass_unique_key": row.key_mill and f"{row.key_mill}-", "miller": row.miller}
		)
		if row_mill != mill:
			continue
		season_text = row.season or row.key_season
		if season_text not in season_of:
			season_of[season_text] = resolve_season_master_name(season_text)
		year = year_of.get(season_of[season_text])
		if year:
			years.add(year)
	return years


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


def get_transit_passes(filters, seasons, to_date):
	"""PPAS Transit Passes of the mill and KMS Year up to To Month, with the PPC in the District.

	Returns (passes, skipped): skipped are passes of the mill and year whose PPC is not in PPC Master
	or has no District. Each pass has ``is_wshg`` of its PPC (see tp_receipts).
	"""
	passes, skipped = [], []
	for row in mill_transit_passes(filters.mill, seasons, to_date):
		if not row.district:
			skipped.append(row)
		elif row.district == filters.paddy_account:
			passes.append(row)
	return passes, skipped


def procured_districts(mill, seasons, to_date):
	"""Districts the mill procured paddy from in the KMS Year: the District in PPC Master of the
	PPC of each of its Transit Passes up to ``to_date``."""
	return {row.district for row in mill_transit_passes(mill, seasons, to_date) if row.district}


def mill_transit_passes(mill, seasons, to_date):
	"""PPAS Transit Passes of the mill in the seasons up to ``to_date``, oldest first, each with
	``district`` and ``is_wshg`` of its PPC in PPC Master (district None when the PPC is not there)."""
	rows = frappe.get_all(
		"PPAS Transit Pass",
		filters={"transit_pass_date": ["<=", to_date]},
		fields=["name", "pass_unique_key", "miller", "season", "ppc", "quantity", "transit_pass_date"],
		order_by="transit_pass_date asc, transit_pass_time asc, creation asc",
		limit_page_length=0,
	)

	season_of, district_of, wshg_of = {}, {}, {}
	passes = []
	for row in rows:
		if mill_id_from_transit_pass(row) != mill:
			continue

		season_text = row.season or season_code_from_pass_key(row.pass_unique_key)
		if season_text not in season_of:
			season_of[season_text] = resolve_season_master_name(season_text)
		if season_of[season_text] not in seasons:
			continue

		if row.ppc not in district_of:
			ppc = resolve_ppc_master_name(row.ppc)
			master = ppc and frappe.db.get_value("PPC Master", ppc, ["district", "is_wshg"], as_dict=True)
			district_of[row.ppc] = master and master.district
			wshg_of[row.ppc] = cint(master and master.is_wshg)
		row.district = district_of[row.ppc]
		row.is_wshg = wshg_of[row.ppc]
		passes.append(row)

	return passes


def season_code_from_pass_key(pass_unique_key):
	"""Season code of a pass key: "M051007-BAKTI(S1050104)-K25-TP45" -> "K25"."""
	parts = (pass_unique_key or "").rsplit("-", 2)
	return parts[1] if len(parts) == 3 else ""


def tp_receipts(passes):
	"""Each transit pass as (Transit Pass Date, column, TP quantity): "wshgs" when its PPC is
	ticked Is WSHG in PPC Master, else "pacs"."""
	return [
		(getdate(tp.transit_pass_date), "wshgs" if tp.get("is_wshg") else "pacs", flt(tp.quantity))
		for tp in passes
		if tp.transit_pass_date
	]


def get_issue_for_milling(filters, to_date):
	"""(date, "issue_for_milling", qty) from the Paddy Stock Register (PVR milling spread over the
	week's days) of the mill, District and KMS Year, both seasons."""
	# Imported here: the Paddy Stock Register imports from this module.
	from ivri_od.procurement.report.paddy_stock_register.paddy_stock_register import (
		get_issue_for_milling as register_issue_for_milling,
	)

	register_filters = frappe._dict(
		mill=filters.mill, kms_year=filters.kms_year, district=filters.paddy_account, season=None
	)
	return [
		(getdate(date), "issue_for_milling", flt(qty))
		for date, _kind, qty in register_issue_for_milling(register_filters, to_date)
	]


def get_dcro_releases(filters, to_date):
	"""Paddy released for milling as (date, "issue_for_milling", qty) (shown as Paddy Released by
	execute), from the DCRO Paddy Release
	rows of the mill and KMS Year: only the District's columns (filters.paddy_account), rejected or
	cancelled orders left out. Rows without a KMS Year are not counted."""
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
		release = dcro_release(cells, skip_status, filters.paddy_account, own_district, districts)
		if release and release[0] <= to_date:
			releases.append(release)
	return releases


def dcro_kms_year(value):
	"""First year of a DCRO KMS Year: "2024-2025", "2024-25" or "24-25" -> 2024; None if unreadable."""
	match = re.fullmatch(r"(\d{2}|\d{4})\s*-\s*(\d{2}|\d{4})", (value or "").strip())
	if not match:
		return None
	first = int(match.group(1))
	return first + 2000 if first < 100 else first


def dcro_release(cells, skip_status, district=None, own_district=None, districts=None):
	"""(date, "issue_for_milling", qty) of one DCRO row, or None without a date or for a rejected order.
	With ``district``: only that district's Paddy Released (Own District is ``own_district``);
	without it, every Paddy Released column added up."""
	status = " ".join(value for header, value in cells.items() if "status" in header.lower()).lower()
	if any(word in status for word in skip_status):
		return None
	release_date = parse_portal_date(cells.get(DCRO_DATE_COLUMN))
	if not release_date:
		return None
	if district:
		qty = released_by_district(cells, own_district, districts or {}).get(district, 0)
	else:
		qty = _sum_of(cells, DCRO_BALANCE["released"])
	return release_date, "issue_for_milling", flt(qty)


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
			if column in OTHERS:
				continue  # Paddy Released does not change stock
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
		for column in RECEIPTS + ISSUES + OTHERS:
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
	for column in RECEIPTS + ISSUES + OTHERS:
		total_row[column] = flt(sum(row[column] for row in month_rows), PRECISION)

	set_totals(total_row)
	total_row["cb"] = month_rows[-1]["cb"]
	return total_row


def get_message(skipped_passes, filters, releases=None):
	messages = []
	if releases is not None and not frappe.db.get_value("Mill Master", filters.mill, "district"):
		# Own District columns cannot be given to a district.
		messages.append(
			_("Set the District of mill {0} in Mill Master: its Own District paddy release is not counted.").format(
				filters.mill
			)
		)
	if skipped_passes:
		ppcs = sorted({tp.ppc for tp in skipped_passes if tp.ppc})
		messages.append(
			_(
				"{0} Transit Passes of mill {1} are not counted because their PPC is not in PPC Master "
				"or has no District: {2}"
			).format(len(skipped_passes), filters.mill, ", ".join(ppcs[:10]) or _("PPC not set"))
		)
	return " ".join(messages) or None
