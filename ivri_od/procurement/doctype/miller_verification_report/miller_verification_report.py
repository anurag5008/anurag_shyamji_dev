# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Verification Report of the Authorised Officer (Annexure-1): paddy and rice stock of a
miller, one Agency row per agency / season, with totals. Locked once submitted.

Typed in every time: I, II, III (paddy milled this week), IX FCI / RRC (rice delivered
this week). VII (rice received this week) is III x FCI rice % (Rice Delivery Setup
"Boiled") for a Par-Boiled mill, and can be changed by hand.

Progressive rows carry on from the previous submitted report of the same Miller Code
and KMS (its row of the same agency and season; 0 for an agency it did not have):
- IV   Prog. paddy milled     = previous IV + III
- VIII Prog. rice received    = previous VIII + VII
- XI   Prog. rice delivered   = previous XI + IX (FCI and RRC)
The first report of a miller / KMS has no previous one: it starts from 0, so IV, VIII and
XI are this week's III, VII and IX. An opening figure typed in (e.g. a miller who started
before the system) is kept.

Miller Code links to Mill Master (1a. Miller Name is its Company); the report's Season and
the Season of each row link to Season Master (e.g. "Kharif 2025"). A new report of a mill
and season is filled from the last submitted one (get_last_report): address, capacity, KMS,
variety, electricity, officer, agencies; its date and present meter reading become this
report's last verification date and last meter reading. A row without a season gets the
report's season (an agency can be given another season from Season Master); KMS, when
empty, is the season's (2025 -> 2025-26). Agencies are added in the Annexure-1 format.
- II   Prog. paddy received   = Target Quantity of every PPC allotted to the mill in Target
  Allocation for the row's season; on the first row of each season. When the mill has no
  Target Allocation for the season, II is typed in.

- X    Prog. DC issued        = lots on the mill's FCI / RRC DCs of the row's season (as
  in DC Track) x Rice Lot Quantity; on the first row of each season. When no
  DC is read for the mill, X is typed in.
- V    Book balance of paddy  = II - IV;          VI  Verified balance of paddy = V
- Prog. CMR Due               = VIII (FRK rule to be confirmed with FSA)
- X / XI Total                = FCI + RRC
- XII  Undelivered            = X - XI (FCI, RRC, Total)
- XIII Book balance of rice   = VIII - XI Total;  XIV Verified balance of rice  = XIII
4d Total Units consumed = (Present reading - Last reading) x Meter Multiplier.
The same sums are made in miller_verification_report.js, to show them while typing
(get_progressive_basis gives it the previous report, Target Allocation paddy and DC lots)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

PRECISION = 3

# Copied from the last report of the same mill and season (get_last_report).
CARRIED_FIELDS = (
	"address",
	"milling_capacity",
	"milling_capacity_uom",
	"kms",
	"variety",
	"contract_load",
	"contract_load_unit",
	"meter_multiplier",
	"miller_representative",
	"authorised_officer",
)

# Agency fields typed in by the officer (or carried on from the previous report).
ENTERED_FIELDS = (
	"paddy_received_week",
	"prog_paddy_received",
	"paddy_milled_week",
	"prog_paddy_milled",
	"rice_received_week",
	"prog_rice_received",
	"frk_percent",
	"frk_qty",
	"rice_delivered_week_fci",
	"rice_delivered_week_rrc",
	"prog_dc_fci",
	"prog_dc_rrc",
	"prog_delivered_fci",
	"prog_delivered_rrc",
)
# Calculated stock that cannot be below 0 (the differences can).
STOCK_FIELDS = (
	"book_balance_paddy",
	"undelivered_fci",
	"undelivered_rrc",
	"undelivered_total",
	"book_balance_rice",
)
# Every quantity of an Agency row with a "total_<field>" on the report (FRK % is not added up).
TOTAL_FIELDS = (
	"paddy_received_week",
	"prog_paddy_received",
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
# Progressive field: (this week's field) added to the previous report's value.
PROGRESSIVE_FIELDS = {
	"prog_paddy_milled": "paddy_milled_week",
	"prog_rice_received": "rice_received_week",
	"prog_delivered_fci": "rice_delivered_week_fci",
	"prog_delivered_rrc": "rice_delivered_week_rrc",
}
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
			frappe.throw(_("Add at least one agency in the Annexure-1 format."))
		self.set_season_defaults()
		self.check_parent_quantities()
		self.calculate_units_consumed()
		basis = progressive_basis(
			self.miller_code, self.kms, self.variety, self.present_verification_date, self.name, self.agencies
		)
		seasons_done = set()
		for row in self.agencies:
			apply_progressive(row, basis, first_of_season=row.season not in seasons_done)
			seasons_done.add(row.season)
			calculate_agency(row)
			self.check_agency_quantities(row)
		self.calculate_totals()
		self.warn_differences()

	def set_season_defaults(self):
		if not self.season:
			return
		if not self.kms:
			self.kms = kms_of_season(self.season)
		for row in self.agencies:
			if not row.season:
				row.season = self.season

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
		meta = frappe.get_meta(row.doctype)
		for field in ENTERED_FIELDS + STOCK_FIELDS:
			if flt(row.get(field)) < 0:
				frappe.throw(
					_("Row {0} ({1}): {2} cannot be negative ({3}).").format(
						row.idx, row.agency, _(meta.get_label(field)), row.get(field)
					)
				)

	def calculate_totals(self):
		for field in TOTAL_FIELDS:
			self.set("total_" + field, flt(sum(flt(row.get(field)) for row in self.agencies), PRECISION))

	def warn_differences(self):
		for row in self.agencies:
			for field, label in (("paddy_difference", _("Paddy")), ("rice_difference", _("Rice"))):
				if flt(row.get(field), PRECISION):
					frappe.msgprint(
						_("Row {0} ({1}): {2} difference is {3} Qtls (verified balance is not the book balance).").format(
							row.idx, row.agency, label, row.get(field)
						),
						title=_("Stock Difference"),
						indicator="orange",
					)


def kms_of_season(season) -> str:
	"""KMS of a Season Master: year 2025 -> "2025-26" (as on the DCs), "" when unknown."""
	year = frappe.db.get_value("Season Master", season, "year") or ""
	return f"{year}-{(int(year) + 1) % 100:02d}" if year.isdigit() else ""


@frappe.whitelist()
def get_last_report(miller_code: str, season: str, name: str = "") -> dict:
	"""For a new report: what to fill in from the last submitted report of the same mill
	and season ({} when there is none). Its present date and meter reading are the new
	report's last ones; its agencies come back with their season (progressive figures
	carry on from it on save, see progressive_basis)."""
	frappe.has_permission("Miller Verification Report", "read", throw=True)
	if not (miller_code and season):
		return {}
	filters = {"docstatus": 1, "miller_code": miller_code, "season": season}
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
		return {"kms": kms_of_season(season)}
	last = last[0]
	values = {field: last.get(field) for field in CARRIED_FIELDS}
	values.update(
		last_report=last.name,
		last_verification_date=last.present_verification_date,
		meter_reading_last=last.meter_reading_present,
		agencies=frappe.get_all(
			"Miller Verification Agency",
			filters={"parent": last.name, "parenttype": "Miller Verification Report"},
			fields=["agency", "season"],
			order_by="idx asc",
		),
	)
	return values


def row_key(agency, season) -> str:
	return f"{(agency or '').strip().casefold()}|{season or ''}"


@frappe.whitelist()
def get_progressive_basis(
	miller_code: str, kms: str, variety: str = "", present_verification_date: str = "", name: str = "", seasons=None
) -> dict:
	"""For the form: the previous report, FCI rice % and the DC quantities (see progressive_basis)."""
	frappe.has_permission("Miller Verification Report", "read", throw=True)
	seasons = frappe.parse_json(seasons) if isinstance(seasons, str) else seasons
	rows = [frappe._dict(season=s) for s in seasons or ()]
	return progressive_basis(miller_code, kms, variety, present_verification_date, name, rows)


def progressive_basis(miller_code, kms, variety, present_verification_date=None, name=None, rows=None) -> dict:
	"""What the progressive rows are built on:
	previous: the previous submitted report of the miller and KMS (name), or None;
	rows: {agency|season: its progressive fields} of that report;
	rice_percentage: FCI rice % (Rice Delivery Setup "Boiled") for a Par-Boiled mill, else None;
	paddy_received: {season: Qtls} = Target Quantity in Target Allocation (seasons with any);
	dc_quantity: {season: {"fci": Qtls, "rrc": Qtls}} = DC lots x Rice Lot Quantity (seasons with DCs read)."""
	basis = frappe._dict(previous=None, rows={}, rice_percentage=None, paddy_received={}, dc_quantity={})
	if not (miller_code and kms):
		return basis

	filters = {"docstatus": 1, "miller_code": miller_code, "kms": kms}
	if name and not name.startswith("new-"):
		filters["name"] = ["!=", name]
	if present_verification_date:
		filters["present_verification_date"] = ["<=", present_verification_date]
	previous = frappe.get_all(
		"Miller Verification Report",
		filters=filters,
		fields=["name"],
		order_by="present_verification_date desc, creation desc",
		limit=1,
	)
	if previous:
		basis.previous = previous[0].name
		for row in frappe.get_all(
			"Miller Verification Agency",
			filters={"parent": basis.previous, "parenttype": "Miller Verification Report"},
			fields=["agency", "season", *PROGRESSIVE_FIELDS],
		):
			basis.rows.setdefault(row_key(row.agency, row.season), {f: flt(row.get(f)) for f in PROGRESSIVE_FIELDS})

	if variety == "Par-Boiled":
		basis.rice_percentage = frappe.db.get_value("Rice Delivery Setup", "Boiled", "cmr_percentage")

	seasons = {r.season for r in rows or [] if r.season}
	basis.paddy_received = _paddy_received(miller_code, seasons)
	basis.dc_quantity = _dc_quantity(miller_code, seasons)
	return basis


def _paddy_received(miller_code, seasons) -> dict:
	"""{season: Qtls}: Target Quantity of every PPC allotted to the mill in the season."""
	if not seasons:
		return {}
	rows = frappe.get_all(
		"Target Allocation",
		filters={"mill_name": miller_code, "season": ["in", list(seasons)]},
		fields=["season", {"SUM": "target_quantity", "as": "qty"}],
		group_by="season",
	)
	return {r.season: flt(r.qty, PRECISION) for r in rows}


def _dc_quantity(miller_code, seasons) -> dict:
	"""{season: {"fci": Qtls, "rrc": Qtls}}: lots on the mill's DCs (DC Track) x Rice Lot Quantity."""
	from ivri_od.procurement.report.dc_details.dc_details import _dc_lots

	lot_quantity = flt(frappe.db.get_single_value("Rice Lot Quantity", "lot_quantity"))
	out = {}
	if not lot_quantity:
		return out
	for season in seasons:
		master = frappe.db.get_value("Season Master", season, ["crop_season", "year"], as_dict=True)
		if not master:
			continue
		lots = _dc_lots(master).get((miller_code or "").upper())
		if lots:
			out[season] = {
				"fci": flt(lots.get("fci_issue", 0) * lot_quantity, PRECISION),
				"rrc": flt(lots.get("rrc_issue", 0) * lot_quantity, PRECISION),
			}
	return out


def apply_progressive(row, basis, first_of_season=True):
	"""Fill VII, the progressive fields (IV, VIII, XI), II and X of one Agency row from ``basis``."""
	if basis.rice_percentage is not None and not flt(row.rice_received_week):
		row.rice_received_week = flt(flt(row.paddy_milled_week) * flt(basis.rice_percentage) / 100, PRECISION)
	if basis.previous:
		previous = basis.rows.get(row_key(row.agency, row.season), {})
		for prog, week in PROGRESSIVE_FIELDS.items():
			row.set(prog, flt(flt(previous.get(prog)) + flt(row.get(week)), PRECISION))
	else:
		# First report: starts from 0 unless an opening figure is typed in.
		for prog, week in PROGRESSIVE_FIELDS.items():
			if not flt(row.get(prog)):
				row.set(prog, flt(row.get(week), PRECISION))
	paddy = basis.paddy_received.get(row.season)
	if paddy is not None and first_of_season:
		row.prog_paddy_received = paddy
	dc = basis.dc_quantity.get(row.season)
	if dc and first_of_season:
		row.prog_dc_fci = dc["fci"]
		row.prog_dc_rrc = dc["rrc"]


def calculate_agency(row):
	"""Fill the calculated fields of one Agency row (rows V, VI, CMR Due, X-XIV, differences)."""

	def v(field):
		return flt(row.get(field))

	def put(field, value):
		row.set(field, flt(value, PRECISION))

	put("book_balance_paddy", v("prog_paddy_received") - v("prog_paddy_milled"))
	put("verified_balance_paddy", v("book_balance_paddy"))
	put("paddy_difference", v("verified_balance_paddy") - v("book_balance_paddy"))
	put("prog_cmr_due", v("prog_rice_received"))
	put("prog_dc_total", v("prog_dc_fci") + v("prog_dc_rrc"))
	put("prog_delivered_total", v("prog_delivered_fci") + v("prog_delivered_rrc"))
	put("undelivered_fci", v("prog_dc_fci") - v("prog_delivered_fci"))
	put("undelivered_rrc", v("prog_dc_rrc") - v("prog_delivered_rrc"))
	put("undelivered_total", v("undelivered_fci") + v("undelivered_rrc"))
	put("book_balance_rice", v("prog_rice_received") - v("prog_delivered_total"))
	put("verified_balance_rice", v("book_balance_rice"))
	put("rice_difference", v("verified_balance_rice") - v("book_balance_rice"))
