# Copyright (c) 2026, Profezzo and contributors
"""Rice Stock Report: monthly OB, rice received from milling, rice delivered to FCI and RRC, and CB.

Filters: Mill Name, KMS Year, From / To Month, District (optional).
- Rice Received from Milling: the Paddy Stock Register's Issue for Milling (date-wise) of the mill
  and KMS Year (every district, or only the District), summed by month, times the Rice Percentage
  (CMR %) of Rice Delivery Setup for the mill's Type in Mill Master (Raw / Boiled).
  (Until 2026-11-04 it was the DCRO paddy released for milling.)
- FCI Delivery: DCRO "DC Transit Challan" rows of the mill and KMS Year, Net Weight by Accepted
  Date month (both read from the row's AC Note), one column per depot ("Depot Code-Depot Name").
- RRC Delivery: SCMS "Lot Search" rows of the mill and KMS Year, Qty by Receipt Date month,
  one column per Depot.
Depot columns: every depot of the mill and KMS Year, also when the District filter leaves it at 0.
Total = OB + Rice Received; Total Delivery = FCI Total + RRC Total; CB = Total - Total Delivery.
Rejected or cancelled rows are left out.
District: RRC rows by Lot Search's own District column (as in Lot Search from SCMS); FCI rows, and
RRC rows without a District, by the mill's DC numbers of that District in DCRO "View DC" (District
read from the DC PDF or set by hand): DC Order No / DC No."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, getdate

from ivri_od.procurement.portal_report import _load, _number
from ivri_od.procurement.portal_sync import (
	ACCEPTED_DATE_COLUMN,
	DISTRICT_COLUMN,
	MOISTURE_CUT_COLUMN,
	NO_DISTRICT,
	_match_key,
)
from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	dcro_kms_year,
	get_issue_for_milling,
	get_months,
	parse_portal_date,
	season_master_year,
)

PRECISION = 2
KMS_COLUMN = "KMS Year"
SKIP_STATUS = ("reject", "cancel")
# DCRO DC Transit Challan
FCI_SECTION = "DC Transit Challan"
FCI_DEPOT_CODE, FCI_DEPOT_NAME = "Depot Code", "Depot Name"
FCI_DC_NO = "DC Order No"
# SCMS Lot Search
RRC_SECTION = "Lot Search"
RRC_DEPOT, RRC_DATE, RRC_QTY = "Depot", "Receipt Date", "Qty(In Qtl.)"
RRC_DC_NO = "DC No."
RRC_DISTRICT = "District"  # SCMS Lot Search page's District (e.g. "BALANGIR")
# DCRO View DC: the DC numbers of a District
VIEW_DC_SECTION = "View DC"
VIEW_DC_NO = "DC Code(RRC)"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	from_date, to_date = validate_filters(filters)
	year = int(season_master_year(filters.kms_year))

	rice_percentage = get_rice_percentage(filters.mill)
	received = get_rice_received(filters.mill, filters.kms_year, to_date, rice_percentage, filters.district)
	dc_numbers, dcs_without_district = get_district_dcs(filters.mill, filters.district)
	fci, fci_without_date, fci_depots = get_deliveries(
		"DCRO", FCI_SECTION, filters.mill, year, to_date, fci_delivery, dc_numbers, FCI_DC_NO
	)
	rrc, rrc_without_date, rrc_depots = get_deliveries(
		"SCMS", RRC_SECTION, filters.mill, year, to_date, rrc_delivery, dc_numbers, RRC_DC_NO,
		filters.district, RRC_DISTRICT,
	)

	columns = get_columns(fci_depots, rrc_depots)
	data = build_rows(get_months(from_date, to_date), from_date, received, fci, rrc, fci_depots, rrc_depots)
	return columns, data, get_message(fci_without_date, rrc_without_date, filters, dcs_without_district)


def validate_filters(filters):
	for fieldname, label in (
		("mill", _("Mill Name")),
		("kms_year", _("KMS Year")),
		("from_month", _("From Month")),
		("to_month", _("To Month")),
	):
		if not filters.get(fieldname):
			frappe.throw(_("{0} is mandatory").format(label))

	filters.company = frappe.db.get_value("Mill Master", filters.mill, "company")
	from_date = getdate(get_first_day(filters.from_month))
	to_date = getdate(get_last_day(filters.to_month))
	if from_date > to_date:
		frappe.throw(_("From Month must be before To Month"))
	return from_date, to_date


def get_rice_percentage(mill):
	"""Rice Percentage (CMR %) of Rice Delivery Setup for the mill's Type (RAW / BOILED)."""
	mill_type = (frappe.db.get_value("Mill Master", mill, "type") or "").strip()
	if not mill_type:
		frappe.throw(_("Set the Type (Raw / Boiled) of mill {0} in Mill Master").format(mill))
	setups = {
		row.name.casefold(): flt(row.cmr_percentage)
		for row in frappe.get_all("Rice Delivery Setup", fields=["name", "cmr_percentage"])
	}
	percentage = setups.get(mill_type.casefold())
	if not percentage:
		frappe.throw(_("Set the Rice Percentage of {0} in Rice Delivery Setup").format(mill_type.title()))
	return percentage


def _rows(site, section, mill, year):
	"""Row cells of the section for the mill and KMS Year (the row's KMS Year column)."""
	for record in frappe.get_all(
		"Portal Record",
		filters={"site": site, "section": section, "mill_id": mill},
		fields=["row_data"],
		order_by="seen_run asc, row_no asc",
		limit_page_length=0,
	):
		cells = _load(record.row_data)
		if dcro_kms_year(cells.get(KMS_COLUMN)) == year:
			yield cells


def get_rice_received(mill, kms_year, to_date, rice_percentage, district=None):
	"""[(date, rice qty)]: Paddy Stock Register's Issue for Milling of the mill and KMS Year
	(every district, or only ``district``) times the rice percentage."""
	register_filters = frappe._dict(mill=mill, kms_year=kms_year, paddy_account=district or None)
	return [
		(issue_date, qty * rice_percentage / 100)
		for issue_date, _column, qty in get_issue_for_milling(register_filters, to_date)
		if issue_date <= to_date
	]


def get_district_dcs(mill, district):
	"""(DC numbers of the mill in the District, View DC rows of the mill without a District),
	from DCRO View DC; (None, 0) without a District filter."""
	if not district:
		return None, 0
	wanted = district.strip().casefold()
	dc_numbers, without_district = set(), 0
	for record in frappe.get_all(
		"Portal Record",
		filters={"site": "DCRO", "section": VIEW_DC_SECTION, "mill_id": mill},
		fields=["row_data"],
		limit_page_length=0,
	):
		cells = _load(record.row_data)
		row_district = (cells.get(DISTRICT_COLUMN) or "").strip()
		if not row_district or row_district == NO_DISTRICT:
			without_district += 1
		elif row_district.casefold() == wanted and (cells.get(VIEW_DC_NO) or "").strip():
			dc_numbers.add(_dc_key(cells.get(VIEW_DC_NO)))
	return dc_numbers, without_district


def _dc_key(value):
	return "".join((value or "").split()).upper()


def get_deliveries(
	site, section, mill, year, to_date, read_row, dc_numbers=None, dc_column=None, district=None, district_column=None
):
	"""([(date, depot, qty)], rows without a date, depots): rows of the section read by ``read_row``.
	With ``dc_numbers`` (District filter): only rows of the District: by the row's own
	``district_column`` when it has one (matched ignoring capitals and spaces), else by its
	``dc_column`` being one of ``dc_numbers``.
	``depots``: every depot of the mill and KMS Year, one column each, whatever the District or dates."""
	deliveries, without_date, depots = [], 0, set()
	for cells in _rows(site, section, mill, year):
		if _skipped(cells):
			continue
		delivery = read_row(cells)
		depots.add(delivery[1])
		if dc_numbers is not None and not _in_district(cells, dc_numbers, dc_column, district, district_column):
			continue
		if not delivery[0]:
			without_date += 1
		elif delivery[0] <= to_date:
			deliveries.append(delivery)
	return deliveries, without_date, sorted(depots, key=str.casefold)


def _in_district(cells, dc_numbers, dc_column, district, district_column):
	own_district = (district_column and cells.get(district_column) or "").strip()
	if own_district:
		return _match_key(own_district) == _match_key(district)
	return _dc_key(cells.get(dc_column)) in dc_numbers


def fci_delivery(cells):
	"""(Accepted Date, "Depot Code-Depot Name", Weight After Moisture Cut) of a DC Transit Challan row
	(the AC Note's own Net Weight, after the Value Cut; not the Purchase Weight shown as Net Weight)."""
	code, name = (cells.get(FCI_DEPOT_CODE) or "").strip(), (cells.get(FCI_DEPOT_NAME) or "").strip()
	depot = "-".join(part for part in (code, name) if part) or _("No Depot")
	return parse_portal_date(cells.get(ACCEPTED_DATE_COLUMN)), depot, flt(_number(cells.get(MOISTURE_CUT_COLUMN)))


def rrc_delivery(cells):
	"""(Receipt Date, Depot, Qty) of a Lot Search row."""
	depot = (cells.get(RRC_DEPOT) or "").strip() or _("No Depot")
	return parse_portal_date(cells.get(RRC_DATE)), depot, flt(_number(cells.get(RRC_QTY)))


def _skipped(cells):
	status = " ".join(v for h, v in cells.items() if "status" in h.lower() and isinstance(v, str)).lower()
	return any(word in status for word in SKIP_STATUS)


def get_columns(fci_depots, rrc_depots):
	def qty(label, fieldname, width=140):
		return {"label": label, "fieldname": fieldname, "fieldtype": "Float", "precision": PRECISION, "width": width}

	columns = [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 90},
		qty(_("OB"), "ob", 120),
		qty(_("Rice Received from Milling"), "rice_received", 180),
		qty(_("Total"), "total", 120),
	]
	columns += [qty(_("FCI: {0}").format(depot), f"fci_{i}", 200) for i, depot in enumerate(fci_depots)]
	columns.append(qty(_("FCI Total"), "fci_total", 120))
	columns += [qty(_("RRC: {0}").format(depot), f"rrc_{i}", 200) for i, depot in enumerate(rrc_depots)]
	columns.append(qty(_("RRC Total"), "rrc_total", 120))
	columns += [qty(_("Total Delivery"), "total_delivery", 130), qty(_("CB"), "cb", 120)]
	return columns


def build_rows(months, from_date, received, fci, rrc, fci_depots, rrc_depots):
	"""One row per month (zero rows included), then the Total row. Movements before From Month make the OB."""
	opening = 0.0
	by_month = defaultdict(lambda: defaultdict(float))
	for movement_date, qty in received:
		if movement_date < from_date:
			opening += qty
		else:
			by_month[movement_date.replace(day=1)]["rice_received"] += qty
	for prefix, deliveries, depots in (("fci", fci, fci_depots), ("rrc", rrc, rrc_depots)):
		fieldname = {depot: f"{prefix}_{i}" for i, depot in enumerate(depots)}
		for movement_date, depot, qty in deliveries:
			if movement_date < from_date:
				opening -= qty
			else:
				by_month[movement_date.replace(day=1)][fieldname[depot]] += qty

	qty_fields = ["rice_received"] + [f"fci_{i}" for i in range(len(fci_depots))] + [f"rrc_{i}" for i in range(len(rrc_depots))]
	rows, balance = [], flt(opening, PRECISION)
	for month in months:
		row = {"month": month.strftime("%b-%y"), "ob": balance}
		for fieldname in qty_fields:
			row[fieldname] = flt(by_month[month].get(fieldname), PRECISION)
		set_totals(row, len(fci_depots), len(rrc_depots))
		balance = row["cb"]
		rows.append(row)

	total_row = {"month": _("Total"), "ob": rows[0]["ob"], "bold": 1}
	for fieldname in qty_fields:
		total_row[fieldname] = flt(sum(row[fieldname] for row in rows), PRECISION)
	set_totals(total_row, len(fci_depots), len(rrc_depots))
	total_row["cb"] = rows[-1]["cb"]
	rows.append(total_row)
	return rows


def set_totals(row, fci_count, rrc_count):
	row["total"] = flt(row["ob"] + row["rice_received"], PRECISION)
	row["fci_total"] = flt(sum(row[f"fci_{i}"] for i in range(fci_count)), PRECISION)
	row["rrc_total"] = flt(sum(row[f"rrc_{i}"] for i in range(rrc_count)), PRECISION)
	row["total_delivery"] = flt(row["fci_total"] + row["rrc_total"], PRECISION)
	row["cb"] = flt(row["total"] - row["total_delivery"], PRECISION)


def get_message(fci_without_date, rrc_without_date, filters=None, dcs_without_district=0):
	messages = []
	filters = filters or frappe._dict()
	if dcs_without_district:
		messages.append(
			_(
				"{0} DCs of mill {1} in View DC from DCRO have no District, so their FCI deliveries "
				"(and RRC lots without a District in Lot Search) are not counted for {2}. "
				"Set their District in that report."
			).format(dcs_without_district, filters.mill, filters.district)
		)
	if fci_without_date:
		messages.append(
			_(
				"{0} DC Transit Challan rows are not counted: they have no Accepted Date (AC Note not downloaded yet)."
			).format(fci_without_date)
		)
	if rrc_without_date:
		messages.append(_("{0} Lot Search rows are not counted: they have no Receipt Date.").format(rrc_without_date))
	return " ".join(messages) or None
