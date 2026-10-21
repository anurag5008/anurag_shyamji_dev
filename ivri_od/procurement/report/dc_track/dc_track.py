# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""DC Track: is each DC fulfilled? One line per DC, joined on the DC number.

- View DC (DCRO) gives the DC: DC No. ("DC Code(RRC)"), mill ("Miller Code"),
  DC date ("Generated Date") and the lots to deliver (the "Lots" read from the DC
  page, see View DC from DCRO).
- The lots delivered are counted from one row per lot:
  FCI DCs (DCF...) in DCRO DC Transit Challan ("DC Order No", "Lot No."),
  RRC DCs (DCR...) in SCMS Lot Search ("DC No.", "Lot No.").
  A lot is counted once (by its Lot No.); a rejected or cancelled row is not counted.
- Remaining Lots = Total Lots - Lots Delivered.
- DC Note: the DC document saved from the View DC row (View_FCI / View_RRC button).
- A click on Lots Delivered opens the delivered lots of the DC (get_delivered_lots) with
  their acknowledgement files: FCI - the Details and AC Note Doc PDFs of the DCRO
  Transit Challan row; RRC - the file saved from the SCMS Lot Search row.
A DC found only in a delivery report (its View DC row not read yet) is still listed,
with status "DC Not in View DC".
Data comes from Portal Data Extraction (agent) -> Portal Record; see procurement/portal_report.py."""

import re

import frappe
from frappe import _

from ivri_od.procurement.portal_report import MAX_RECORDS, _date_sort_key, _detail_sum, _get_details, _key, _load
from ivri_od.procurement.portal_sync import NOISE_HEADER

DC_SOURCE = ("DCRO", "View DC")
# (site, section, label shown in "Delivered From")
DELIVERY_SOURCES = [
	("DCRO", "DC Transit Challan", "DCRO Transit Challan"),
	("SCMS", "Lot Search", "SCMS Lot Search"),
]

# Column headers (letters and digits only, lower case) in the order they are tried.
DC_NO = ["dccoderrc", "dccode", "dcorderno", "dcno", "dcnumber"]
LOT_NO = ["lotno", "lotnumber"]
MILL = ["millercode", "millcode", "millerid", "millid"]
MILL_NAME = ["millername", "millname"]
DC_DATE = ["generateddate", "dcdate", "date"]
STATUS = ["pendingat", "challanstatus", "status"]
DELIVERY_DATE = ["receiptdate", "transitchallandate"]

# A delivery row with this status does not count as a delivered lot.
NOT_DELIVERED = re.compile(r"reject|cancel", re.IGNORECASE)

# Lots pop-up: portal columns holding only button text, not shown (their files are links).
BUTTON_COLUMNS = {"details", "delete", "acnotedoc", "print", "action"}
# Lots pop-up: name of each saved file. Portal Record "documents" labels (FCI: DCRO
# DC Transit Challan); "receipt" is the file saved from the row (RRC: SCMS Lot Search).
FILE_LABELS = {"Details": "Details", "AC Note Doc": "Acknowledgement Note", "receipt": "Acknowledgement"}
# Files each delivery source should have: shown as "Not saved" when not read yet.
SOURCE_FILES = {"DCRO Transit Challan": ["Details", "Acknowledgement Note"], "SCMS Lot Search": ["Acknowledgement"]}

FULFILLED = "Fulfilled"
PARTLY = "Partly Delivered"
NOT_STARTED = "Not Started"
OVER = "Over Delivered"
LOTS_NOT_READ = "Lots Not Read"
# The DC page shows 0 lots (nothing to deliver), e.g. a DC that was not used.
NO_LOTS = "No Lots on DC"
NOT_IN_VIEW_DC = "DC Not in View DC"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	dcs = _dcs_from_view_dc()
	_add_deliveries(dcs)

	data = [_line(dc) for dc in dcs.values()]
	data = [row for row in data if _matches(row, filters)]
	data.sort(key=lambda r: (r["dc_date"] or "", r["dc_no"]), reverse=True)
	return _columns(), data, None, None, _summary(data)


def _dcs_from_view_dc() -> dict:
	"""{DC No.: dc} from every saved View DC row."""
	records = _records(*DC_SOURCE)
	details = _get_details([r.name for r in records]) if records else {}
	dcs = {}
	for record in records:
		cells = _load(record.row_data)
		dc_no = _dc_no(_cell(cells, DC_NO))
		if not dc_no:
			continue
		rows = details.get(record.name) or []
		total = _detail_sum(rows, ["lots"])
		dcs[dc_no] = _dc(
			dc_no,
			mill_id=_cell(cells, MILL) or record.mill_id or "",
			mill_name=_cell(cells, MILL_NAME),
			kms_year=_cell(cells, ["kmsyear", "kms"]),
			season=_cell(cells, ["season"]),
			dc_date=_iso_date(_cell(cells, DC_DATE)),
			dc_type=_dc_type(dc_no, cells, rows),
			total_lots=None if total is None else int(total),
			in_view_dc=True,
			dc_note=record.receipt_file or "",
		)
	return dcs


def _add_deliveries(dcs: dict):
	"""Count each DC's delivered lots from the delivery reports (one row per lot)."""
	for site, section, label in DELIVERY_SOURCES:
		for record in _records(site, section):
			cells = _load(record.row_data)
			dc_no = _dc_no(_cell(cells, DC_NO))
			if not dc_no:
				continue
			dc = dcs.get(dc_no)
			if dc is None:
				dc = dcs[dc_no] = _dc(
					dc_no,
					mill_id=_cell(cells, MILL) or record.mill_id or "",
					mill_name=_cell(cells, MILL_NAME),
					kms_year=_cell(cells, ["kmsyear", "kms"]),
					dc_type=_dc_type(dc_no, cells, []),
				)
			dc["sources"].add(label)
			if NOT_DELIVERED.search(_cell(cells, STATUS)):
				dc["not_counted"] += 1
				continue
			# A lot read twice (e.g. sent again) counts once; a row without Lot No. counts by itself.
			dc["lots"].add(_cell(cells, LOT_NO) or record.name)
			delivered_on = _iso_date(_cell(cells, DELIVERY_DATE))
			if delivered_on and delivered_on > (dc["last_delivery"] or ""):
				dc["last_delivery"] = delivered_on


def _dc(dc_no, **values) -> dict:
	dc = {
		"dc_no": dc_no,
		"mill_id": "",
		"mill_name": "",
		"kms_year": "",
		"season": "",
		"dc_date": None,
		"dc_type": "",
		"total_lots": None,
		"in_view_dc": False,
		"lots": set(),
		"not_counted": 0,
		"sources": set(),
		"last_delivery": None,
		"dc_note": "",
	}
	dc.update(values)
	return dc


def _line(dc) -> dict:
	delivered = len(dc["lots"])
	total = dc["total_lots"]
	remaining = None if total is None else total - delivered
	if not dc["in_view_dc"]:
		status = NOT_IN_VIEW_DC
	elif total is None:
		status = LOTS_NOT_READ
	elif total == 0 and not delivered:
		status = NO_LOTS
	elif remaining == 0:
		status = FULFILLED
	elif remaining < 0:
		status = OVER
	elif delivered:
		status = PARTLY
	else:
		status = NOT_STARTED
	return {
		"mill_id": dc["mill_id"],
		"mill_name": dc["mill_name"],
		"dc_no": dc["dc_no"],
		"dc_date": dc["dc_date"],
		"dc_type": dc["dc_type"],
		"dc_note": dc["dc_note"],
		"kms_year": dc["kms_year"],
		"season": dc["season"],
		"total_lots": total,
		"delivered_lots": delivered,
		"remaining_lots": remaining,
		"status": status,
		"delivered_lot_nos": ", ".join(sorted(dc["lots"], key=_lot_sort_key)),
		"not_counted": dc["not_counted"],
		"last_delivery": dc["last_delivery"],
		"delivered_from": ", ".join(sorted(dc["sources"])),
	}


def _matches(row, filters) -> bool:
	if filters.mill_id and row["mill_id"].lower() != filters.mill_id.strip().lower():
		return False
	if filters.dc_no and filters.dc_no.strip().upper() not in row["dc_no"]:
		return False
	if filters.dc_type and row["dc_type"] != filters.dc_type:
		return False
	if filters.status and row["status"] != filters.status:
		return False
	if filters.from_date and (not row["dc_date"] or row["dc_date"] < str(filters.from_date)):
		return False
	if filters.to_date and (not row["dc_date"] or row["dc_date"] > str(filters.to_date)):
		return False
	return True


def _records(site, section, like=None):
	"""Saved rows of a section (``like``: only rows whose data holds this text, e.g. a DC No.)."""
	filters = {"site": site, "section": section}
	if like:
		filters["row_data"] = ["like", f"%{like}%"]
	return frappe.get_list(
		"Portal Record",
		filters=filters,
		fields=["name", "row_data", "mill_id", "receipt_file", "documents"],
		limit_page_length=MAX_RECORDS,
	)


def _cell(cells: dict, keys) -> str:
	"""Value of the first header (compared as letters and digits) in ``keys``."""
	by_key = {}
	for header, value in cells.items():
		by_key.setdefault(_key(header), value)
	for key in keys:
		value = (by_key.get(key) or "").strip()
		if value:
			return value
	return ""


def _dc_no(value) -> str:
	return re.sub(r"\s+", "", value or "").upper()


def _dc_type(dc_no, cells, details) -> str:
	"""FCI or RRC: the DC page's "DC Type", else the View_FCI / View_RRC button, else DCF / DCR."""
	for row in details:
		kind = (row.get("DC Type") or "").strip().upper()
		if kind in ("FCI", "RRC"):
			return kind
	for kind in ("FCI", "RRC"):
		if re.match(r"view", cells.get(kind) or "", re.IGNORECASE):
			return kind
	return {"DCF": "FCI", "DCR": "RRC"}.get(dc_no[:3], "")


def _iso_date(value):
	"""dd-mm-yyyy or dd/mm/yyyy as yyyy-mm-dd, else None."""
	kind, when = _date_sort_key(value)
	return when.strftime("%Y-%m-%d") if kind == 0 else None


def _lot_sort_key(lot):
	return (0, int(lot), "") if lot.isdigit() else (1, 0, lot)


def _columns():
	return [
		{"fieldname": "mill_id", "label": _("Mill No."), "fieldtype": "Data", "width": 110},
		{"fieldname": "mill_name", "label": _("Mill Name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "dc_no", "label": _("DC No."), "fieldtype": "Data", "width": 120},
		{"fieldname": "dc_date", "label": _("DC Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "dc_type", "label": _("DC Type"), "fieldtype": "Data", "width": 80},
		# The DC document saved from View DC: a download link (see dc_track.js).
		{"fieldname": "dc_note", "label": _("DC Note"), "fieldtype": "Data", "width": 100},
		{"fieldname": "kms_year", "label": _("KMS Year"), "fieldtype": "Data", "width": 90},
		{"fieldname": "season", "label": _("Season"), "fieldtype": "Data", "width": 80},
		{"fieldname": "total_lots", "label": _("Total Lots"), "fieldtype": "Int", "width": 90},
		# A click opens the delivered lots with their acknowledgement files (get_delivered_lots).
		{"fieldname": "delivered_lots", "label": _("Lots Delivered"), "fieldtype": "Int", "width": 110},
		{"fieldname": "remaining_lots", "label": _("Remaining Lots to Deliver"), "fieldtype": "Int", "width": 120},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 140},
		{"fieldname": "delivered_lot_nos", "label": _("Delivered Lot Nos."), "fieldtype": "Data", "width": 200},
		{"fieldname": "not_counted", "label": _("Rejected / Cancelled"), "fieldtype": "Int", "width": 100},
		{"fieldname": "last_delivery", "label": _("Last Receipt Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "delivered_from", "label": _("Delivered From"), "fieldtype": "Data", "width": 170},
	]


def _summary(data):
	def count(status):
		return sum(1 for r in data if r["status"] == status)

	remaining = sum(r["remaining_lots"] for r in data if (r["remaining_lots"] or 0) > 0)
	return [
		{"label": _("DCs"), "value": len(data), "indicator": "Blue", "datatype": "Int"},
		{"label": _(FULFILLED), "value": count(FULFILLED), "indicator": "Green", "datatype": "Int"},
		{"label": _(PARTLY), "value": count(PARTLY), "indicator": "Orange", "datatype": "Int"},
		{"label": _(NOT_STARTED), "value": count(NOT_STARTED), "indicator": "Red", "datatype": "Int"},
		{"label": _("Remaining Lots"), "value": remaining, "indicator": "Red", "datatype": "Int"},
	]


@frappe.whitelist()
def get_delivered_lots(dc_no: str) -> dict:
	"""Lots pop-up of one DC: every delivery row read for it (FCI: DCRO DC Transit
	Challan, RRC: SCMS Lot Search) as the portal shows it, with how it is counted
	in Lots Delivered and links to its saved files (acknowledgement, details)."""
	dc_no = _dc_no(dc_no)
	if not dc_no:
		frappe.throw(_("DC No. is missing"))
	view_dc = [r for r in _records(*DC_SOURCE, like=dc_no) if _dc_no(_cell(_load(r.row_data), DC_NO)) == dc_no]

	lots, seen = [], set()
	for site, section, label in DELIVERY_SOURCES:
		for record in _records(site, section, like=dc_no):
			cells = _load(record.row_data)
			if _dc_no(_cell(cells, DC_NO)) != dc_no:
				continue
			lot_no = _cell(cells, LOT_NO)
			# Same rule as Lots Delivered: rejected / cancelled rows and a lot read twice are not counted.
			if NOT_DELIVERED.search(_cell(cells, STATUS)):
				counted = _("Rejected / Cancelled")
			elif (lot_no or record.name) in seen:
				counted = _("Read Twice")
			else:
				seen.add(lot_no or record.name)
				counted = _("Counted")
			lots.append(
				{
					"lot_no": lot_no,
					"counted": counted,
					"source": label,
					"cells": {
						h: v for h, v in cells.items() if not NOISE_HEADER.match(h) and _key(h) not in BUTTON_COLUMNS
					},
					"files": _files(record),
				}
			)
	lots.sort(key=lambda lot: _lot_sort_key(lot["lot_no"]))
	return {
		"dc_no": dc_no,
		"dc_type": _dc_type(dc_no, _load(view_dc[0].row_data), []) if view_dc else _dc_type(dc_no, {}, []),
		"dc_note": view_dc[0].receipt_file if view_dc else "",
		"counted": len(seen),
		"lots": lots,
		"file_labels": [
			_(label) for source in dict.fromkeys(lot["source"] for lot in lots) for label in SOURCE_FILES.get(source, [])
		],
	}


def _files(record) -> list[dict]:
	"""[{label, url}] of the files saved from a delivery row's buttons."""
	files = [
		{"label": _(FILE_LABELS.get(label, label)), "url": url} for label, url in _load(record.documents).items() if url
	]
	if record.receipt_file:
		files.append({"label": _(FILE_LABELS["receipt"]), "url": record.receipt_file})
	return files
