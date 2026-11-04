# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Verification Report of the Authorised Officer (Annexure-1): paddy and rice stock of a
miller, one column per District and Season (Kharif / Rabi) of the KMS Year, with totals.
Locked once submitted.

Only the Present Verification Date, V and FRK are typed in. The other figures are worked out
from the data read from the portals, for the column's District and Season of the KMS Year (e.g. 2025-26:
Kharif 2025, Rabi 2025). The data is taken up to the day before the Present Verification Date
(data_up_to): "till date" is up to that day; "during the week" is the period from the Last
Verification Date (the last submitted report of the mill and KMS Year; its own day is
counted here, as that report stopped the day before) up to that day; without a Last
Verification Date the period is everything up to that day.
- I / II    Paddy received:  PPAS Transit Passes of the mill and season whose PPC is in the
            District in PPC Master (as Stock Account for Paddy), by Transit Pass Date.
- III / IV  Paddy released for milling: DCRO Paddy Release of the mill, KMS Year and Season,
            the column's District's Paddy Released (Own District = the mill's District in Mill
            Master; see dcro_paddy_release.py), by Date of Requistion; rejected or cancelled
            orders count 0. IV adds up every release up to data_up_to.
- V         Paddy milled during the week: typed in.
- VI        Prog. paddy milled:  VI of the same District and Season of the last submitted report
            of the mill and KMS Year (0 without one) + V.
- IX        Rice received:  V x Rice Percentage for FCI (CMR %) of Rice Delivery Setup for the
            mill's Type (as Rice Stock Report).
- X         Prog. rice received: X of the last report (as VI) + IX.
- XII       Prog. DC issued:  DCRO View DC of the mill: lots of each DC (Generated Date up to the
            Present Verification Date) x Rice Lot Quantity, by DC Type (FCI / RRC), for DCs whose
            District (read from the DC PDF or set by hand; for an RRC DC without one, the District
            of its Lot Search rows) and Season are the column's.
- XI / XIII  Rice delivered:  FCI - DCRO DC Transit Challan Net Weight by Accepted Date; RRC -
            SCMS Lot Search Qty by Receipt Date. A row's District and Season are those of its DC
            in View DC; an RRC row's District is the Lot Search page's own District when it has one.
- VII = II - VI;  VIII = VII;  Prog. CMR Due = X;  XII / XIII Total = FCI + RRC;
  XIV = XII - XIII;  XV = X - XIII Total;  XVI = XV.
- FRK % and FRK Quantity have no source yet: typed in.
Rows that cannot be given to a column (no date, DC not in View DC, DC without a District)
are not counted and are listed as notes.
4d Total Units consumed = (Present reading - Last reading) x Meter Multiplier.
A new report is filled from the last submitted report of the same mill and KMS Year
(get_last_report): address, capacity, electricity, officer and its District / Season columns;
its date and present meter reading become this report's last ones.
A draft also gets a column for every District and Season of the KMS Year that has portal data
of the mill (Transit Passes, Paddy Release, View DC; get_data_columns), e.g. Balangir Kharif, Balangir Rabi and, once its data is read,
Koraput Kharif; columns are only added, never removed."""

from collections import defaultdict
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate

from ivri_od.procurement.dcro_paddy_release import (
	DATE_COLUMN as RELEASE_DATE_COLUMN,
	KMS_COLUMN as RELEASE_KMS_COLUMN,
	SEASON_COLUMN as RELEASE_SEASON_COLUMN,
	district_names,
	released_by_district,
)
from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.portal_report import _detail_sum, _get_details, _load
from ivri_od.procurement.portal_sync import DISTRICT_COLUMN, NO_DISTRICT, _match_key
from ivri_od.procurement.report.dc_track.dc_track import DC_DATE, _cell, _dc_no, _dc_type
from ivri_od.procurement.report.rice_stock_report.rice_stock_report import (
	FCI_DC_NO,
	FCI_SECTION,
	RRC_DC_NO,
	RRC_DISTRICT,
	RRC_SECTION,
	_skipped,
	fci_delivery,
	get_rice_percentage,
	rrc_delivery,
)
from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	dcro_kms_year,
	get_transit_passes,
	parse_portal_date,
	season_code_from_pass_key,
)
from ivri_od.procurement.transit_pass_resolve import mill_id_from_transit_pass, resolve_ppc_master_name

PRECISION = 3
SEASONS = ("Kharif", "Rabi")
VIEW_DC = ("DCRO", "View DC")
PADDY_RELEASE = ("DCRO", "Paddy Release")
VARIETY_OF_TYPE = {"boiled": "Par-Boiled", "raw": "Raw"}

# Copied from the last report of the same mill and KMS Year (get_last_report).
CARRIED_FIELDS = (
	"address",
	"milling_capacity",
	"milling_capacity_uom",
	"contract_load",
	"contract_load_unit",
	"meter_multiplier",
	"miller_representative",
	"authorised_officer",
)
# Column figures worked out from the portal data (annexure_figures).
SOURCE_FIELDS = (
	"paddy_received_week",
	"prog_paddy_received",
	"paddy_released_week",
	"prog_paddy_released",
	"rice_delivered_week_fci",
	"rice_delivered_week_rrc",
	"prog_dc_fci",
	"prog_dc_rrc",
	"prog_delivered_fci",
	"prog_delivered_rrc",
)
# Cumulative figures carried from the last report's column (last_cumulative) and added to.
CUMULATIVE_FIELDS = ("prog_paddy_milled", "prog_rice_received")
# Typed in, cannot be negative.
TYPED_FIELDS = ("paddy_milled_week", "frk_percent", "frk_qty")
# Calculated stock that cannot be below 0 (the differences can).
STOCK_FIELDS = (
	"book_balance_paddy",
	"undelivered_fci",
	"undelivered_rrc",
	"undelivered_total",
	"book_balance_rice",
)
# Every quantity of a column with a "total_<field>" on the report (FRK % is not added up).
TOTAL_FIELDS = (
	"paddy_received_week",
	"prog_paddy_received",
	"paddy_released_week",
	"prog_paddy_released",
	"paddy_milled_week",
	"prog_paddy_milled",
	"book_balance_paddy",
	"verified_balance_paddy",
	"paddy_difference",
	"rice_received_week",
	"prog_rice_received",
	"frk_qty",
	"prog_cmr_due",
	"rice_delivered_week_fci",
	"rice_delivered_week_rrc",
	"rice_delivered_week_total",
	"prog_dc_fci",
	"prog_dc_rrc",
	"prog_dc_total",
	"prog_delivered_fci",
	"prog_delivered_rrc",
	"prog_delivered_total",
	"undelivered_fci",
	"undelivered_rrc",
	"undelivered_total",
	"book_balance_rice",
	"verified_balance_rice",
	"rice_difference",
)
PARENT_QTY_FIELDS = (
	"milling_capacity",
	"contract_load",
	"meter_reading_last",
	"meter_reading_present",
	"meter_multiplier",
	"total_cmr_delivered_m_reporting",
)


class MillerVerificationReport(Document):
	def validate(self):
		if not self.agencies:
			frappe.throw(_("Add at least one District and Season in the Annexure-1 format."))
		self.set_defaults()
		self.check_columns()
		self.check_parent_quantities()
		self.calculate_units_consumed()
		columns = [(row.district, row.season) for row in self.agencies]
		figures, notes = annexure_figures(
			self.miller_code, self.kms, columns, self.present_verification_date, self.last_verification_date
		)
		last = last_cumulative(self.miller_code, self.kms, columns, self.present_verification_date, self.name)
		percentage = get_rice_percentage(self.miller_code)
		for row, values, opening in zip(self.agencies, figures, last):
			row.update(values)
			calculate_agency(row, opening, percentage)
			self.check_agency_quantities(row)
		self.calculate_totals()
		self.warn_differences()
		for note in notes:
			frappe.msgprint(note, title=_("Not Counted"), indicator="orange")

	def set_defaults(self):
		if not self.variety and self.miller_code:
			mill_type = (frappe.db.get_value("Mill Master", self.miller_code, "type") or "").strip().casefold()
			self.variety = VARIETY_OF_TYPE.get(mill_type)
		if not self.last_verification_date:
			self.last_verification_date = previous_verification_date(
				self.miller_code, self.kms, self.present_verification_date, self.name
			)
		for row in self.agencies:
			# The column heading (print format) is the District.
			row.agency = row.district

	def check_columns(self):
		if dcro_kms_year(self.kms) is None:
			frappe.throw(_("2a. KMS Year must look like 2025-26"))
		if self.last_verification_date and getdate(self.last_verification_date) >= getdate(
			self.present_verification_date
		):
			frappe.throw(_("3a. Last Verification Date must be before 3b. Present Verification Date."))
		seen = set()
		for row in self.agencies:
			key = (row.district, row.season)
			if key in seen:
				frappe.throw(_("{0} {1} is added twice in Annexure-1.").format(row.district, row.season))
			seen.add(key)

	def check_parent_quantities(self):
		for field in PARENT_QTY_FIELDS:
			if flt(self.get(field)) < 0:
				frappe.throw(_("{0} cannot be negative.").format(_(self.meta.get_label(field))))
		if flt(self.meter_reading_present) < flt(self.meter_reading_last):
			frappe.throw(
				_("4c. Present meter reading ({0}) cannot be less than 4b. Meter reading at last verification ({1}).").format(
					self.meter_reading_present, self.meter_reading_last
				)
			)

	def calculate_units_consumed(self):
		multiplier = flt(self.meter_multiplier) if self.meter_multiplier is not None else 1
		self.total_units_consumed = flt(
			(flt(self.meter_reading_present) - flt(self.meter_reading_last)) * multiplier, PRECISION
		)

	def check_agency_quantities(self, row):
		"""Typed figures (V, FRK) cannot be negative. A negative stock worked out from the portal data
		(e.g. paddy milled before its Transit Passes are read) is shown, not refused."""
		meta = frappe.get_meta(row.doctype)
		for field in TYPED_FIELDS:
			if flt(row.get(field)) < 0:
				frappe.throw(
					_("{0} {1}: {2} cannot be negative ({3}).").format(
						row.district, row.season, _(meta.get_label(field)), row.get(field)
					)
				)
		for field in STOCK_FIELDS:
			if flt(row.get(field), PRECISION) < 0:
				frappe.msgprint(
					_("{0} {1}: {2} is below 0 ({3}). Check that all portal data is read.").format(
						row.district, row.season, _(meta.get_label(field)), row.get(field)
					),
					title=_("Negative Stock"),
					indicator="orange",
				)

	def calculate_totals(self):
		for field in TOTAL_FIELDS:
			self.set("total_" + field, flt(sum(flt(row.get(field)) for row in self.agencies), PRECISION))

	def warn_differences(self):
		for row in self.agencies:
			for field, label in (("paddy_difference", _("Paddy")), ("rice_difference", _("Rice"))):
				if flt(row.get(field), PRECISION):
					frappe.msgprint(
						_("{0} {1}: {2} difference is {3} Qtls (verified balance is not the book balance).").format(
							row.district, row.season, label, row.get(field)
						),
						title=_("Stock Difference"),
						indicator="orange",
					)


def previous_verification_date(miller_code, kms, present_date, name=None):
	"""Present Verification Date of the last submitted report of the mill and KMS Year before ``present_date``."""
	last = previous_report(miller_code, kms, present_date, name)
	return last and last.present_verification_date


def previous_report(miller_code, kms, present_date, name=None):
	"""Name and Present Verification Date of the last submitted report of the mill and KMS Year
	before ``present_date``, or None."""
	if not (miller_code and kms and present_date):
		return None
	filters = {
		"docstatus": 1,
		"miller_code": miller_code,
		"kms": kms,
		"present_verification_date": ["<", present_date],
	}
	if name and not name.startswith("new-"):
		filters["name"] = ["!=", name]
	return frappe.db.get_value(
		"Miller Verification Report",
		filters,
		["name", "present_verification_date"],
		as_dict=True,
		order_by="present_verification_date desc",
	)


def last_cumulative(miller_code, kms, columns, present_date, name=None) -> list[dict]:
	"""[{CUMULATIVE_FIELDS: Qtls} per column (District, Season)] of the same column of the last
	submitted report (0 when there is no report or the column is not in it)."""
	out = [dict.fromkeys(CUMULATIVE_FIELDS, 0.0) for _column in columns]
	last = previous_report(miller_code, kms, present_date, name)
	if not last:
		return out
	rows = frappe.get_all(
		"Miller Verification Agency",
		filters={"parent": last.name, "parenttype": "Miller Verification Report"},
		fields=["district", "season", *CUMULATIVE_FIELDS],
	)
	for values, (district, season) in zip(out, columns):
		for row in rows:
			if _match_key(row.district) == _match_key(district) and (row.season or "") == (season or ""):
				values.update({field: flt(row.get(field)) for field in CUMULATIVE_FIELDS})
				break
	return out


@frappe.whitelist()
def get_kms_years() -> list[str]:
	"""KMS Years of Season Master, newest first: year 2025 (Kharif 2025, Rabi 2025) is "2025-26"."""
	years = {int(year) for year in frappe.get_all("Season Master", pluck="year") if (year or "").isdigit()}
	return [f"{year}-{(year + 1) % 100:02d}" for year in sorted(years, reverse=True)]


@frappe.whitelist()
def get_last_report(miller_code: str, kms: str, name: str = "") -> dict:
	"""For a new report: what to fill in from the last submitted report of the same mill and
	KMS Year ({} when there is none): its details, District / Season columns, and its present
	date and meter reading as this report's last ones."""
	frappe.has_permission("Miller Verification Report", "read", throw=True)
	if not (miller_code and kms):
		return {}
	filters = {"docstatus": 1, "miller_code": miller_code, "kms": kms}
	if name and not name.startswith("new-"):
		filters["name"] = ["!=", name]
	last = frappe.get_all(
		"Miller Verification Report",
		filters=filters,
		fields=["name", "present_verification_date", "meter_reading_present", *CARRIED_FIELDS],
		order_by="present_verification_date desc, creation desc",
		limit=1,
	)
	if not last:
		return {}
	last = last[0]
	values = {field: last.get(field) for field in CARRIED_FIELDS}
	values.update(
		last_report=last.name,
		last_verification_date=last.present_verification_date,
		meter_reading_last=last.meter_reading_present,
		agencies=frappe.get_all(
			"Miller Verification Agency",
			filters={"parent": last.name, "parenttype": "Miller Verification Report"},
			fields=["district", "season"],
			order_by="idx asc",
		),
	)
	return values


@frappe.whitelist()
def get_data_columns(miller_code: str, kms: str) -> list[dict]:
	"""[{district, season}] of every District and Season (Kharif / Rabi) of the KMS Year with portal
	data of the mill, from the same sources as the figures: Transit Passes (District of the PPC
	in PPC Master), Paddy Release (districts with a quantity released), View DC (District and Season of the DC; an RRC DC without a District takes
	its Lot Search rows' District). Districts as spelt in District Master; by District, Kharif first."""
	frappe.has_permission("Miller Verification Report", "read", throw=True)
	year = dcro_kms_year(kms)
	if not (miller_code and year):
		return []
	known = {_match_key(name): name for name in district_names().values()}
	found = set()

	def found_in(district, season):
		district = known.get(_match_key(district))
		season = next((s for s in SEASONS if s.casefold() == (season or "").strip().casefold()), None)
		if district and season:
			found.add((district, season))

	crop_of = dict(
		frappe.get_all("Season Master", filters={"year": str(year)}, fields=["name", "crop_season"], as_list=True)
	)
	master_of, district_of = {}, {}
	for row in frappe.get_all(
		"PPAS Transit Pass", fields=["miller", "season", "ppc", "pass_unique_key"], limit_page_length=0
	):
		if mill_id_from_transit_pass(row) != miller_code:
			continue
		season_text = row.season or season_code_from_pass_key(row.pass_unique_key)
		if season_text not in master_of:
			master_of[season_text] = resolve_season_master_name(season_text)
		if master_of[season_text] not in crop_of:
			continue
		if row.ppc not in district_of:
			ppc = resolve_ppc_master_name(row.ppc)
			district_of[row.ppc] = ppc and frappe.db.get_value("PPC Master", ppc, "district")
		found_in(district_of[row.ppc], crop_of[master_of[season_text]])

	for district, season, _when, qty in mill_releases(miller_code, year):
		if qty:
			found_in(district, season)

	dcs = _Figures(miller_code, year, [], None, None).view_dcs()
	for cells in _section_rows(("SCMS", RRC_SECTION), miller_code):
		dc = dcs.get(_dc_no(cells.get(RRC_DC_NO)))
		if dc and not dc.district:
			dc.district = (cells.get(RRC_DISTRICT) or "").strip()
	for dc in dcs.values():
		if dc.year == year:
			found_in(dc.district, dc.season)

	return [
		{"district": district, "season": season}
		for district, season in sorted(found, key=lambda c: (c[0], SEASONS.index(c[1])))
	]


@frappe.whitelist()
def get_figures(
	miller_code: str,
	kms: str,
	present_verification_date: str,
	last_verification_date: str = "",
	columns=None,
	name: str = "",
) -> dict:
	"""For the form: the figures of each column [{district, season}] (see annexure_figures),
	the cumulative VI / X of the last report (last_cumulative), the Rice Percentage, the
	notes, and the Last Verification Date used."""
	frappe.has_permission("Miller Verification Report", "read", throw=True)
	columns = frappe.parse_json(columns) if isinstance(columns, str) else columns or []
	last_date = last_verification_date or previous_verification_date(
		miller_code, kms, present_verification_date, name
	)
	columns = [(c.get("district"), c.get("season")) for c in columns]
	figures, notes = annexure_figures(miller_code, kms, columns, present_verification_date, last_date)
	return {
		"rows": figures,
		"last": last_cumulative(miller_code, kms, columns, present_verification_date, name),
		"rice_percentage": get_rice_percentage(miller_code) if miller_code else 0,
		"notes": notes,
		"last_verification_date": last_date,
		"data_up_to": data_up_to(present_verification_date),
	}


def data_up_to(present_date):
	"""Last day whose data a report counts: the day before its Present Verification Date."""
	return add_days(getdate(present_date), -1) if present_date else None


def annexure_figures(miller_code, kms, columns, present_date, last_date=None) -> tuple[list[dict], list[str]]:
	"""([{SOURCE_FIELDS: Qtls} per column], notes) for columns [(District, Season)] of the KMS Year."""
	empty = [dict.fromkeys(SOURCE_FIELDS, 0.0) for _column in columns]
	year = dcro_kms_year(kms)
	if not (miller_code and year and present_date and columns):
		return empty, []
	present = data_up_to(present_date)
	period_start = getdate(last_date) if last_date else None
	data = _Figures(miller_code, year, columns, period_start, present)
	data.paddy_received()
	data.paddy_released()
	data.dc_issued_and_delivered()
	return [
		{field: flt(data.out[column].get(field), PRECISION) for field in SOURCE_FIELDS} for column in data.columns
	], data.notes


class _Figures:
	"""The figures of each (District, Season) column, read from the portal data."""

	def __init__(self, mill, year, columns, period_start, present):
		self.mill, self.year, self.period_start, self.present = mill, year, period_start, present
		self.columns = [(district or "", season or "") for district, season in columns]
		self.out = {column: defaultdict(float) for column in self.columns}
		self.notes = []

	def column(self, district, season):
		"""The column of a District and Season (matched ignoring capitals and spaces), or None."""
		for column in self.columns:
			if _match_key(column[0]) == _match_key(district) and column[1].casefold() == (season or "").strip().casefold():
				return column
		return None

	def add(self, column, when, week_field, prog_field, qty):
		"""Add a quantity dated ``when``: to the progressive figure up to data_up_to (``present``), and
		to the period's ("during the week") figure from the Last Verification Date on (every date
		when there is none)."""
		if column is None or when is None or when > self.present:
			return
		self.out[column][prog_field] += flt(qty)
		if week_field and (self.period_start is None or when >= self.period_start):
			self.out[column][week_field] += flt(qty)

	def paddy_received(self):
		"""I / II: PPAS Transit Passes of the season with the PPC in the District."""
		skipped = set()
		for district, season in self.columns:
			master = frappe.db.get_value("Season Master", {"crop_season": season, "year": str(self.year)}, "name")
			if not master:
				self.notes.append(_("No Season Master {0} {1}: paddy received is not counted.").format(season, self.year))
				continue
			passes, without_district = get_transit_passes(
				frappe._dict(mill=self.mill, paddy_account=district), [master], self.present
			)
			skipped.update(tp.name for tp in without_district)
			for tp in passes:
				self.add(
					(district, season), getdate(tp.transit_pass_date), "paddy_received_week", "prog_paddy_received", tp.quantity
				)
		if skipped:
			self.notes.append(
				_("{0} Transit Passes are not counted: their PPC is not in PPC Master or has no District.").format(
					len(skipped)
				)
			)

	def paddy_released(self):
		"""III / IV: DCRO Paddy Release of the KMS Year, each district's Paddy Released in the
		column of that District and the row's Season."""
		without_date = 0
		for district, season, when, qty in mill_releases(self.mill, self.year):
			if when is None:
				without_date += 1
				continue
			self.add(self.column(district, season), when, "paddy_released_week", "prog_paddy_released", qty)
		if without_date:
			self.notes.append(
				_("{0} Paddy Release rows are not counted: they have no {1}.").format(without_date, RELEASE_DATE_COLUMN)
			)

	def dc_issued_and_delivered(self):
		"""XII: lots of the View DC DCs x Rice Lot Quantity. XI / XIII: FCI and RRC deliveries."""
		dcs = self.view_dcs()
		rrc_rows = list(_section_rows(("SCMS", RRC_SECTION), self.mill))
		# An RRC DC without a District in View DC takes the District of its Lot Search rows, so
		# XII counts every DC that XIII counts deliveries against.
		for cells in rrc_rows:
			dc = dcs.get(_dc_no(cells.get(RRC_DC_NO)))
			district = (cells.get(RRC_DISTRICT) or "").strip()
			if dc and district and not dc.district:
				dc.district = district
		lot_quantity = flt(frappe.db.get_single_value("Rice Lot Quantity", "lot_quantity"))
		no_district, no_lots = 0, 0
		for dc in dcs.values():
			if dc.year != self.year:
				continue
			if not dc.district:
				no_district += 1
				continue
			column = self.column(dc.district, dc.season)
			if column and dc.lots is None:
				no_lots += 1
			elif dc.kind in ("fci", "rrc"):
				self.add(column, dc.date or self.present, None, f"prog_dc_{dc.kind}", (dc.lots or 0) * lot_quantity)
		if no_district:
			self.notes.append(
				_("{0} DCs of the KMS Year have no District in View DC from DCRO: not counted. Set their District there.").format(
					no_district
				)
			)
		if no_lots:
			self.notes.append(_("{0} DCs have no lots read yet: XII. Prog. DC issued leaves them out.").format(no_lots))
		if not lot_quantity:
			self.notes.append(_("Set the Lot Quantity in Rice Lot Quantity: XII. Prog. DC issued is 0."))

		fci_rows = _section_rows(("DCRO", FCI_SECTION), self.mill)
		self.deliveries(dcs, fci_rows, fci_delivery, FCI_DC_NO, None, "fci")
		self.deliveries(dcs, rrc_rows, rrc_delivery, RRC_DC_NO, RRC_DISTRICT, "rrc")

	def deliveries(self, dcs, rows, read_row, dc_column, district_column, kind):
		"""XI / XIII of one kind: each delivery row in the column of its DC's District and Season."""
		label = _("DC Transit Challan") if kind == "fci" else _("Lot Search")
		without_dc, without_date = 0, 0
		for cells in rows:
			if dcro_kms_year(cells.get("KMS Year")) != self.year or _skipped(cells):
				continue
			when, _depot, qty = read_row(cells)
			dc = dcs.get(_dc_no(cells.get(dc_column)))
			district = (district_column and (cells.get(district_column) or "").strip()) or (dc and dc.district)
			if not (dc and district):
				without_dc += 1
				continue
			if when is None:
				without_date += 1
				continue
			self.add(
				self.column(district, dc.season), when, f"rice_delivered_week_{kind}", f"prog_delivered_{kind}", qty
			)
		if without_dc:
			self.notes.append(
				_("{0} {1} rows are not counted: their DC is not in View DC from DCRO or has no District.").format(
					without_dc, label
				)
			)
		if without_date:
			self.notes.append(
				_("{0} {1} rows are not counted: they have no {2} yet.").format(
					without_date, label, _("Accepted Date") if kind == "fci" else _("Receipt Date")
				)
			)

	def view_dcs(self) -> dict:
		"""{DC No.: dc} of the mill's View DC rows: District, Season, KMS year, date, kind, lots."""
		records = frappe.get_all(
			"Portal Record",
			filters={"site": VIEW_DC[0], "section": VIEW_DC[1], "mill_id": self.mill},
			fields=["name", "row_data"],
			limit_page_length=0,
		)
		details = _get_details([r.name for r in records]) if records else {}
		dcs = {}
		for record in records:
			cells = _load(record.row_data)
			dc_no = _dc_no(_cell(cells, ["dccoderrc", "dccode", "dcno"]))
			if not dc_no:
				continue
			rows = details.get(record.name) or []
			district = (cells.get(DISTRICT_COLUMN) or "").strip()
			lots = _detail_sum(rows, ["lots"])
			dcs[dc_no] = frappe._dict(
				district="" if district == NO_DISTRICT else district,
				season=_cell(cells, ["season"]),
				year=dcro_kms_year(_cell(cells, ["kmsyear", "kms"])),
				date=parse_portal_date(_cell(cells, DC_DATE)),
				kind=_dc_type(dc_no, cells, rows).lower(),
				lots=None if lots is None else int(lots),
			)
		return dcs


def mill_releases(mill, year):
	"""(district, season, Date of Requistion or None, Qtls) of each district's Paddy Released in
	the mill's DCRO Paddy Release rows of the KMS Year (rejected or cancelled orders: 0)."""
	own_district = frappe.db.get_value("Mill Master", mill, "district")
	districts = district_names()
	for cells in _section_rows(PADDY_RELEASE, mill):
		if dcro_kms_year(cells.get(RELEASE_KMS_COLUMN)) != year:
			continue
		season = (cells.get(RELEASE_SEASON_COLUMN) or "").strip()
		when = parse_portal_date(cells.get(RELEASE_DATE_COLUMN))
		for district, qty in released_by_district(cells, own_district, districts).items():
			yield district, season, when, qty


def _section_rows(source, mill):
	for record in frappe.get_all(
		"Portal Record",
		filters={"site": source[0], "section": source[1], "mill_id": mill},
		fields=["row_data"],
		order_by="seen_run asc, row_no asc",
		limit_page_length=0,
	):
		yield _load(record.row_data)


def calculate_agency(row, last, percentage):
	"""Fill the calculated fields of one column (rows VI-X, CMR Due, XII-XVI, differences) from
	the typed V, the last report's cumulative figures ``last`` and the Rice Percentage."""

	def v(field):
		return flt(row.get(field))

	def put(field, value):
		row.set(field, flt(value, PRECISION))

	put("paddy_milled_week", v("paddy_milled_week"))  # blank is 0
	put("prog_paddy_milled", flt(last.get("prog_paddy_milled")) + v("paddy_milled_week"))
	put("rice_received_week", v("paddy_milled_week") * flt(percentage) / 100)
	put("prog_rice_received", flt(last.get("prog_rice_received")) + v("rice_received_week"))
	put("book_balance_paddy", v("prog_paddy_received") - v("prog_paddy_milled"))
	put("verified_balance_paddy", v("book_balance_paddy"))
	put("paddy_difference", v("verified_balance_paddy") - v("book_balance_paddy"))
	put("prog_cmr_due", v("prog_rice_received"))
	put("rice_delivered_week_total", v("rice_delivered_week_fci") + v("rice_delivered_week_rrc"))
	put("prog_dc_total", v("prog_dc_fci") + v("prog_dc_rrc"))
	put("prog_delivered_total", v("prog_delivered_fci") + v("prog_delivered_rrc"))
	put("undelivered_fci", v("prog_dc_fci") - v("prog_delivered_fci"))
	put("undelivered_rrc", v("prog_dc_rrc") - v("prog_delivered_rrc"))
	put("undelivered_total", v("undelivered_fci") + v("undelivered_rrc"))
	put("book_balance_rice", v("prog_rice_received") - v("prog_delivered_total"))
	put("verified_balance_rice", v("book_balance_rice"))
	put("rice_difference", v("verified_balance_rice") - v("book_balance_rice"))
