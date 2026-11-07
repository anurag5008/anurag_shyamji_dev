# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Save rows scraped from government portals (SCMS, DCRO, WINGS) into Portal Record.

Each row is matched by a stable key so a re-extraction inserts new rows,
updates changed rows and skips unchanged ones. A bad row is logged and
skipped; it never stops the rest of the batch.

Personal identifiers (Aadhaar, PAN, bank account) are dropped before saving:
company policy forbids keeping them in the ERP.
"""

import base64
import binascii
import hashlib
import json
import re
from datetime import datetime
from io import BytesIO

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime
from frappe.utils.messages import clear_last_message

MAX_ROWS_PER_CALL = 100
MAX_COLUMNS = 100
MAX_CELL_LENGTH = 2000
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
MAX_LOG_LENGTH = 50000
SUMMARY_LENGTH = 140
MAX_DETAIL_ROWS = 500

# Columns never stored (company data policy).
SENSITIVE_HEADER = re.compile(
	r"aadha+r|\buid\b|\bpan\b|pan ?(no|card|number)|account ?(no|number)|a/c|\bacc ?no|ifsc",
	re.IGNORECASE,
)
# Filter values that mean "nothing chosen" (e.g. "--Select--").
PLACEHOLDER_VALUE = re.compile(r"^[-\s]*(select|choose)\b", re.IGNORECASE)
# Columns that change between searches without the record changing: row serial
# numbers and button columns ("View", "Print", Action). Ignored for matching and not shown in reports.
NOISE_HEADER = re.compile(
	r"^(s\.? ?no\.?|sl\.? ?(no\.?|#)?|sr\.? ?no\.?|serial( no\.?)?|#|column \d+|action|actions|print)$",
	re.IGNORECASE,
)


def normalize_cells(cells) -> dict[str, str]:
	"""Clean one scraped row: string headers and values, single spaces, size limits."""
	if not isinstance(cells, dict):
		frappe.throw(_("Row data must be a column → value map"))
	if len(cells) > MAX_COLUMNS:
		frappe.throw(_("Row has more than {0} columns").format(MAX_COLUMNS))

	clean = {}
	for header, value in cells.items():
		header = _squash(header)
		if not header or SENSITIVE_HEADER.search(header):
			continue
		clean[header] = _squash(value)[:MAX_CELL_LENGTH]
	if not any(clean.values()):
		frappe.throw(_("Row is empty"))
	return clean


def parse_key_columns(key_columns: str | None) -> list[str]:
	return [c.strip() for c in (key_columns or "").split(",") if c.strip()]


def meaningful_cells(cells: dict[str, str]) -> dict[str, str]:
	"""Cells without serial-number and link-only columns."""
	return {h: v for h, v in cells.items() if not NOISE_HEADER.match(h)}


def build_record_key(cells: dict[str, str], key_columns: list[str]) -> str:
	"""Business key of a row: the key columns if all are filled, else the whole row
	(minus serial and link columns, so a new Sl# does not make a duplicate)."""
	if key_columns:
		by_header = {h.lower(): v for h, v in cells.items()}
		values = [by_header.get(col.lower(), "") for col in key_columns]
		if all(values):
			return " | ".join(values)
	return json.dumps(meaningful_cells(cells), sort_keys=True, ensure_ascii=False)


def build_row_hash(cells: dict[str, str]) -> str:
	return _hash(meaningful_cells(cells))


def build_details_hash(details: list[dict[str, str]]) -> str:
	return _hash([meaningful_cells(d) for d in details])


def normalize_details(details) -> list[dict[str, str]]:
	"""Clean the detail rows (e.g. lots of a DC) scraped from the row's View link."""
	if not isinstance(details, list):
		frappe.throw(_("Detail rows must be a list"))
	clean = []
	for item in details[:MAX_DETAIL_ROWS]:
		try:
			clean.append(normalize_cells(item))
		except frappe.ValidationError:
			continue  # skip empty detail rows
	return clean


def _hash(value) -> str:
	return hashlib.sha1(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def kms_year_from_season_year(value: str) -> str:
	"""DCRO View DC shows the season's year in "KMS (Year)"; saved as the KMS year it
	belongs to: 2026 -> 2025-26, 2025 -> 2024-25. Anything else (e.g. 2025-26) is kept."""
	value = (value or "").strip()
	if not re.fullmatch(r"(19|20)\d\d", value):
		return value
	year = int(value)
	return f"{year - 1}-{year % 100:02d}"


# Cells rewritten when a row of the section is saved (read from the portal or entered
# by hand): {section: {column key (letters and digits): function}}.
SECTION_CELL_FIXES = {
	"View DC": {"kmsyear": kms_year_from_season_year, "kms": kms_year_from_season_year},
}


def fix_section_cells(section: str, cells: dict[str, str]) -> dict[str, str]:
	fixes = SECTION_CELL_FIXES.get(section)
	if not fixes:
		return cells
	out = {}
	for header, value in cells.items():
		fix = fixes.get(re.sub(r"[^a-z0-9]", "", header.lower()))
		out[header] = fix(value) if fix else value
	return out


# DCRO DC Transit Challan: columns read from the row's FCI AC Note:
# - "Acceptance Note No": "Acceptance Note - 208" -> 208.
# - "Net Weight": the Purchase Weight ("Purchase Weight (Quintal/Kg) including 20 kg deduction : 289.73600").
# - "Weight After Moisture Cut": the AC Note's own "Net Weight : 287.41811" (after the Value Cut).
# - "Accepted Date" ("Date of Acceptance 11-May-2026" saved as 11-05-2026) and "Moisture"
#   ("Moisture Value 14.80000"; blank without an AC Note, never set by hand).
# Without an AC Note (no file, a scanned image, or no weights on it) both weights show the Net
# Quantity of "If FCI AC Not Available" and Accepted Date stays blank, unless they were set by hand
# in the report (portal_manual.set_ac_note_values); the AC Note's values always come first.
# {(site, section): document label}. The columns are not part of the record key.
ACCEPTANCE_NOTE_COLUMN = "Acceptance Note No"
NET_WEIGHT_COLUMN = "Net Weight"
MOISTURE_CUT_COLUMN = "Weight After Moisture Cut"
ACCEPTED_DATE_COLUMN = "Accepted Date"
MOISTURE_COLUMN = "Moisture"
NET_WEIGHT_SECTIONS = {("DCRO", "DC Transit Challan"): "AC Note Doc"}
AC_NOTE_COLUMNS = (ACCEPTANCE_NOTE_COLUMN, NET_WEIGHT_COLUMN, MOISTURE_CUT_COLUMN, ACCEPTED_DATE_COLUMN, MOISTURE_COLUMN)
NET_WEIGHT_MASTER = "If FCI AC Not Available"
DEFAULT_NET_QUANTITY = 287.5
# The AC Note's "Net Weight : 287.41811": saved as Weight After Moisture Cut.
NET_WEIGHT_TEXT = re.compile(r"Net\s*Weight\s*:?\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
PURCHASE_WEIGHT_TEXT = re.compile(
	r"Purchase\s*Weight[^:]{0,80}:\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE
)
ACCEPTANCE_NOTE_TEXT = re.compile(r"Acceptance\s*Note\s*[-:]?\s*(\d+)", re.IGNORECASE)
ACCEPTED_DATE_TEXT = re.compile(
	r"Date\s*of\s*Acceptance\s*:?\s*(\d{1,2}[-/ ](?:[A-Za-z]{3,9}|\d{1,2})[-/ ]\d{4})", re.IGNORECASE
)
# "Moisture Value" only: the test table below it also has "Moisture Content 15.00 14.80".
MOISTURE_TEXT = re.compile(r"Moisture\s*Value\s*:?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def ac_note_text(content: bytes | None) -> str:
	"""Text of an AC Note PDF; "" for no file, a scanned image or an unreadable PDF."""
	if not isinstance(content, bytes) or not content.startswith(b"%PDF"):
		return ""
	try:
		from pypdf import PdfReader

		return " ".join(page.extract_text() or "" for page in PdfReader(BytesIO(content)).pages)
	except Exception:
		return ""


def ac_note_net_weight(content: bytes | None) -> str:
	"""Net Weight of an AC Note PDF: its Purchase Weight, as on the PDF ("289.73600"); "" when not found."""
	return _purchase_weight_in(ac_note_text(content))


def ac_note_accepted_date(content: bytes | None) -> str:
	"""Date of Acceptance on an AC Note PDF as dd-mm-yyyy ("11-May-2026" -> "11-05-2026"); "" when not found."""
	return _accepted_date_in(ac_note_text(content))


def _net_weight_in(text: str) -> str:
	"""The AC Note's own "Net Weight" (after the Value Cut): the Weight After Moisture Cut."""
	match = NET_WEIGHT_TEXT.search(text)
	return match.group(1).replace(",", "") if match else ""


def _purchase_weight_in(text: str) -> str:
	match = PURCHASE_WEIGHT_TEXT.search(text)
	return match.group(1).replace(",", "") if match else ""


def _acceptance_note_in(text: str) -> str:
	match = ACCEPTANCE_NOTE_TEXT.search(text)
	return match.group(1) if match else ""


def _moisture_in(text: str) -> str:
	match = MOISTURE_TEXT.search(text)
	return match.group(1) if match else ""


def _accepted_date_in(text: str) -> str:
	match = ACCEPTED_DATE_TEXT.search(text)
	if not match:
		return ""
	value = re.sub(r"[/ ]", "-", match.group(1))
	for date_format in ("%d-%b-%Y", "%d-%B-%Y", "%d-%m-%Y"):
		try:
			return datetime.strptime(value, date_format).strftime("%d-%m-%Y")
		except ValueError:
			continue
	return ""


def default_net_weight() -> str:
	"""Net Quantity of "If FCI AC Not Available", same format as the portal ("287.50000")."""
	value = flt(frappe.db.get_single_value(NET_WEIGHT_MASTER, "net_quantity")) or DEFAULT_NET_QUANTITY
	return f"{value:.5f}"


def add_net_weight(site: str, section: str, cells: dict[str, str], row: dict, record_name: str) -> dict[str, str]:
	"""Add the Acceptance Note No, Net Weight, Weight After Moisture Cut, Accepted Date and Moisture
	columns to a row of a NET_WEIGHT_SECTIONS section. The AC Note sent with the row is read; else
	the one saved before on the record (e.g. its download failed this time); else the values set by
	hand (net_weight_manual, accepted_date_manual: both weights), else the master's Net Quantity
	(both weights) and no Accepted Date."""
	label = NET_WEIGHT_SECTIONS.get((site, section))
	if not label:
		return cells
	text = ac_note_text(_sent_document(row, label))
	if not (_purchase_weight_in(text) or _net_weight_in(text)):
		text = ac_note_text(_saved_document(record_name, label))
	manual = manual_ac_note_values(record_name)
	fallback = manual[NET_WEIGHT_COLUMN] or default_net_weight()
	cells = {h: v for h, v in cells.items() if h not in AC_NOTE_COLUMNS}  # same column order on every read
	return {
		**cells,
		ACCEPTANCE_NOTE_COLUMN: _acceptance_note_in(text),
		NET_WEIGHT_COLUMN: _purchase_weight_in(text) or fallback,
		MOISTURE_CUT_COLUMN: _net_weight_in(text) or fallback,
		ACCEPTED_DATE_COLUMN: _accepted_date_in(text) or manual[ACCEPTED_DATE_COLUMN],
		MOISTURE_COLUMN: _moisture_in(text),
	}


def manual_ac_note_values(record_name: str) -> dict[str, str]:
	"""Net Weight and Accepted Date set by hand on a record, as shown ("287.50000", dd-mm-yyyy); "" when not set."""
	saved = (
		record_name
		and frappe.db.get_value(
			"Portal Record", record_name, ["net_weight_manual", "accepted_date_manual"], as_dict=True
		)
	) or frappe._dict()
	return {
		NET_WEIGHT_COLUMN: f"{flt(saved.net_weight_manual):.5f}" if flt(saved.net_weight_manual) else "",
		ACCEPTED_DATE_COLUMN: getdate(saved.accepted_date_manual).strftime("%d-%m-%Y")
		if saved.accepted_date_manual
		else "",
	}


def without_net_weight(site: str, section: str, cells: dict[str, str]) -> dict[str, str]:
	"""Row cells as read from the portal (the record key is made from these)."""
	if (site, section) not in NET_WEIGHT_SECTIONS:
		return cells
	return {h: v for h, v in cells.items() if h not in AC_NOTE_COLUMNS}


# DCRO View DC: one search brings DCs of many districts, so the page's District filter is not
# enough. The "District" column is read from the DC's PDF ("... on behalf of OSCSC(BALANGIR) ...")
# and saved as spelt in District Master (matched ignoring capitals, small letters and spaces).
# No PDF, or its district is not in the master: "No District Matched". A District set by hand
# in the report (portal_manual.set_dc_district) is kept on later reads. Not part of the record key.
DISTRICT_COLUMN = "District"
NO_DISTRICT = "No District Matched"
DISTRICT_SECTIONS = {("DCRO", "View DC")}
DC_DISTRICT_TEXT = re.compile(r"on\s*behalf\s*of\s*OSCSC\s*\(\s*([^)]+?)\s*\)", re.IGNORECASE)


def dc_district(content: bytes | None) -> str:
	"""District of a View DC PDF as in District Master ("Balangir"); "" when not found."""
	return _master_district(_dc_district_in(ac_note_text(content)))


def _dc_district_in(text: str) -> str:
	match = DC_DISTRICT_TEXT.search(text)
	return _squash(match.group(1)) if match else ""


def _master_district(value: str) -> str:
	wanted = _match_key(value)
	if not wanted:
		return ""
	for name in frappe.get_all("District Master", filters={"is_active": 1}, pluck="name"):
		if _match_key(name) == wanted:
			return name
	return ""


def add_dc_district(site: str, section: str, cells: dict[str, str], row: dict, record_name: str) -> dict[str, str]:
	"""Set the District column of a row of a DISTRICT_SECTIONS section from the DC PDF sent with
	the row, else from the PDF saved before on the record (e.g. not downloaded this time),
	else NO_DISTRICT. A District set by hand in the report (district_manual) is always kept."""
	if (site, section) not in DISTRICT_SECTIONS:
		return cells
	saved = frappe.db.get_value(
		"Portal Record", record_name, ["receipt_file", "district_manual", "row_data"], as_dict=True
	) or frappe._dict()
	if saved.district_manual:
		district = _load_json(saved.row_data).get(DISTRICT_COLUMN) or NO_DISTRICT
	else:
		district = dc_district(_sent_receipt(row)) or dc_district(_saved_file(saved.receipt_file)) or NO_DISTRICT
	return with_district(cells, district)


def with_district(cells: dict[str, str], district: str) -> dict[str, str]:
	if DISTRICT_COLUMN in cells:
		return {**cells, DISTRICT_COLUMN: district}
	# Before the portal columns, with the other search filters.
	return {DISTRICT_COLUMN: district, **cells}


# SCMS Lot Search: the "Vehicle No" column is read from the lot's Print PDF (the acceptance note), table
# "12. VEHICLE DETAILS", column "Vehicle Registration No.". A lot with two vehicles gives "OD03AB4135, OD03AC3255".
# Every read that has the PDF (sent now, or saved before on the record) sets it again; no PDF keeps the value
# already saved. The column is not part of the record key.
VEHICLE_COLUMN = "Vehicle No"
# "1. Acceptance Note No. DW051105 / 0481 / 2025-2026": the number between the two slashes (0481) is the A.C. Note No.
LOT_AC_NOTE_COLUMN = "A.C. Note No."
LOT_AC_NOTE_TEXT = re.compile(r"Acceptance\s*Note\s*No\.?\s*:?\s*[A-Z0-9]+\s*/\s*([A-Z0-9]+)\s*/", re.IGNORECASE)
VEHICLE_SECTIONS = {("SCMS", "Lot Search")}
VEHICLE_AFTER_COLUMN = "Lot No."
VEHICLE_BLOCK_TEXT = re.compile(r"VEHICLE\s*DETAILS(.*?)(?=\n\s*1[3-9]\.\s|\Z)", re.IGNORECASE | re.DOTALL)
VEHICLE_NUMBER_TEXT = re.compile(r"\b[A-Z]{2}\s?\d{1,2}\s?[A-Z]{0,3}\s?\d{4}\b")


def lot_vehicle_numbers(content: bytes | None) -> str:
	"""Vehicle Registration No. of a Lot Search PDF ("OD03AB4135"); "" when there is no PDF or no vehicle on it."""
	return _vehicles_in(ac_note_text(content))


def _vehicles_in(text: str) -> str:
	block = VEHICLE_BLOCK_TEXT.search(text or "")
	if not block:
		return ""
	found = []
	# the header line ("Sl# Challan No. Vehicle Registration No. ...") has no number; the rows have
	for match in VEHICLE_NUMBER_TEXT.finditer(block.group(1).upper()):
		number = re.sub(r"\s", "", match.group(0))
		if number not in found:
			found.append(number)
	return ", ".join(found)


def lot_ac_note_no(content: bytes | None) -> str:
	"""A.C. Note No of a Lot Search PDF ("0481" of "DW051105 / 0481 / 2025-2026", as written); "" when not found."""
	return _lot_ac_note_in(ac_note_text(content))


def _lot_ac_note_in(text: str) -> str:
	match = LOT_AC_NOTE_TEXT.search(text or "")
	return match.group(1) if match else ""


def add_lot_vehicle(site: str, section: str, cells: dict[str, str], row: dict, record_name: str) -> dict[str, str]:
	"""Set the Vehicle No and A.C. Note No columns of a row of a VEHICLE_SECTIONS section from the PDF sent with the
	row, else from the PDF saved before on the record, else the values saved before (else empty)."""
	if (site, section) not in VEHICLE_SECTIONS:
		return cells
	saved = frappe.db.get_value("Portal Record", record_name, ["receipt_file", "row_data"], as_dict=True) or frappe._dict()
	before = _load_json(saved.row_data)
	sent = ac_note_text(_sent_receipt(row))
	stored = ac_note_text(_saved_file(saved.receipt_file)) if saved.receipt_file else ""
	vehicle = _vehicles_in(sent) or _vehicles_in(stored) or before.get(VEHICLE_COLUMN, "")
	ac_note = _lot_ac_note_in(sent) or _lot_ac_note_in(stored) or before.get(LOT_AC_NOTE_COLUMN, "")
	return with_vehicle(cells, vehicle, ac_note)


def with_vehicle(cells: dict[str, str], vehicle: str, ac_note: str = "") -> dict[str, str]:
	"""The Vehicle No and A.C. Note No columns right after the Lot No. column (same position on every read)."""
	cells = {h: v for h, v in cells.items() if h not in (VEHICLE_COLUMN, LOT_AC_NOTE_COLUMN)}
	out = {}
	placed = False
	for header, value in cells.items():
		out[header] = value
		if header == VEHICLE_AFTER_COLUMN:
			out[VEHICLE_COLUMN] = vehicle
			out[LOT_AC_NOTE_COLUMN] = ac_note
			placed = True
	if not placed:
		out[VEHICLE_COLUMN] = vehicle
		out[LOT_AC_NOTE_COLUMN] = ac_note
	return out


def _sent_receipt(row: dict) -> bytes | None:
	receipt = row.get("receipt") or {}
	if not receipt.get("content_b64"):
		return None
	try:
		return base64.b64decode(receipt["content_b64"], validate=True)
	except (binascii.Error, ValueError):
		return None


def _sent_document(row: dict, label: str) -> bytes | None:
	for document in row.get("documents") or []:
		if document and _match_key(document.get("label")) == _match_key(label) and document.get("content_b64"):
			try:
				return _decode_file(document["content_b64"])[0]
			except frappe.ValidationError:
				clear_last_message()
				return None
	return None


def _saved_document(record_name: str, label: str) -> bytes | None:
	return _saved_file(_load_json(frappe.db.get_value("Portal Record", record_name, "documents")).get(label))


def _saved_file(file_url: str | None) -> bytes | None:
	file_name = file_url and frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		return None
	try:
		content = frappe.get_doc("File", file_name).get_content()
	except Exception:
		return None
	# A file whose bytes read as UTF-8 comes back as text.
	return content.encode() if isinstance(content, str) else content


def build_record_name(site: str, section: str, record_key: str, mill_id: str = "") -> str:
	"""Deterministic name so the database itself blocks duplicate rows. With a mill
	the name is the mill's own: two mills never share a record."""
	parts = [site, section, record_key] + ([mill_id] if mill_id else [])
	raw = "\x1f".join(parts).encode()
	return "PR-" + hashlib.sha1(raw).hexdigest()[:20]


def resolve_record_name(site: str, section: str, record_key: str, mill_id: str = "") -> str:
	"""Name of the record for this key and mill. A record saved before mills were
	tracked (name without mill) stays in use for its mill: one with no mill yet is
	taken over by the first mill that reads it again; another mill gets its own record."""
	name = build_record_name(site, section, record_key, mill_id)
	if not mill_id or frappe.db.exists("Portal Record", name):
		return name
	legacy = build_record_name(site, section, record_key)
	saved = frappe.db.get_value("Portal Record", legacy, "mill_id", as_dict=True)
	if saved and (saved.mill_id or "") in ("", mill_id):
		return legacy
	return name


DEFAULT_MILL_LABELS = "Mill ID, Mill Code, Miller Code, Miller ID"


def mill_label_keys(labels: str | None) -> list[str]:
	"""The site's "Mill ID Labels" as letters-and-digits keys: "Miller Code" -> "millercode"."""
	return [re.sub(r"[^a-z0-9]", "", t.lower()) for t in re.split(r"[,\n]", labels or DEFAULT_MILL_LABELS) if t.strip()]


# Columns holding the mill's name with its code at the end, e.g. WINGS TEC "Mill":
# "SHREE SHYAMJI PADDY PROCESSING PVT LTD - 41498".
MILL_NAME_HEADERS = {"mill", "miller", "millname", "millername", "millnamecode", "millernamecode", "millernameandcode"}
NAME_WITH_CODE = re.compile(r"[-–(:]\s*([A-Za-z]{0,4}\d[\w/-]{1,29})\)?\s*$")


def row_mill_id(cells: dict[str, str], label_keys: list[str], session_mill: str = "") -> str:
	"""The mill of a row. ``session_mill`` is the Mill No. picked on Portal Data
	Extraction (one portal account per mill): it is the mill of every row, so all
	reports show the Mill Master code, also on WINGS where the portal has its own
	mill codes. A row whose own mill column (e.g. View DC "Miller Code") names
	another mill of Mill Master is refused: the mills' data is never mixed.
	Without ``session_mill`` (rows saved before Mill No. was asked): the row's own
	mill column, or the code at the end of WINGS TEC "Mill"."""
	own = ""
	for header, value in cells.items():
		if value and re.sub(r"[^a-z0-9]", "", header.lower()) in label_keys:
			own = _squash(value)[:60]
			break
	if not own:
		for header, value in cells.items():
			match = NAME_WITH_CODE.search(value or "")
			if match and re.sub(r"[^a-z0-9]", "", header.lower()) in MILL_NAME_HEADERS:
				own = match.group(1)
				break
	session_mill = _squash(session_mill)[:60]
	if not session_mill:
		return own
	if own and own.upper() != session_mill.upper() and frappe.db.exists("Mill Master", own):
		frappe.throw(
			_("this row is of mill {0}, not of the Mill No. picked ({1}). Log in with the account of {1}.").format(
				own, session_mill
			)
		)
	return session_mill


def build_summary(cells: dict[str, str], key_columns: list[str]) -> str:
	by_header = {h.lower(): v for h, v in cells.items()}
	parts = [by_header.get(c.lower(), "") for c in key_columns]
	parts = [p for p in parts if p] or [v for v in cells.values() if v][:3]
	return " · ".join(parts)[:SUMMARY_LENGTH]


def parse_filter_columns(filter_columns: str | None) -> list[tuple[str, str]]:
	"""Section's "Page Filter Columns": lines "Column Name = words in the filter's label or id"
	("#id": the element with exactly that id, e.g. DCRO Paddy Release KMS Year = #INTKMS)."""
	out = []
	for line in (filter_columns or "").splitlines():
		name, _sep, match = line.partition("=")
		name = _squash(name)
		if name:
			out.append((name, _squash(match) or name))
	return out


def page_field_ids(filter_columns: str | None) -> list[str]:
	"""Element ids named as "#id" in Page Filter Columns: the agent (version 22) reads these
	elements whatever they are (text, label, hidden or read-only box), not only filters."""
	return [match[1:] for _name, match in parse_filter_columns(filter_columns) if match.startswith("#") and match[1:]]


def safe_page_filters(page_filters) -> list[dict]:
	"""Search filters read from the page, without personal identifiers (company data policy)."""
	out = []
	for item in page_filters if isinstance(page_filters, list) else []:
		if not isinstance(item, dict):
			continue
		label, field_id = _squash(item.get("label"))[:80], _squash(item.get("id"))[:80]
		if SENSITIVE_HEADER.search(f"{label} {field_id}"):
			continue
		out.append({"label": label, "id": field_id, "value": _squash(item.get("value"))[:MAX_CELL_LENGTH]})
	return out[:MAX_COLUMNS]


def filter_cells(filter_columns: str | None, page_filters) -> dict[str, str]:
	"""Values of the search filters (e.g. KMS Year, Depot) read from the portal page,
	named as in the section's "Page Filter Columns"."""
	page_filters = safe_page_filters(page_filters)
	cells = {}
	for name, match in parse_filter_columns(filter_columns):
		if name == "*":
			# Every filter under its own label (e.g. DCRO View DC: District, Season, Status...).
			for item in page_filters:
				label = re.sub(r"\s*[:*]+\s*$", "", item["label"] or item["id"])
				if label and item["value"] and not PLACEHOLDER_VALUE.match(item["value"]):
					cells.setdefault(label, item["value"])
			continue
		by_id = match.startswith("#")
		wanted = _match_key(match)
		for item in page_filters:
			if not isinstance(item, dict):
				continue
			value = _squash(item.get("value"))
			if by_id:
				found = _match_key(item.get("id")) == wanted
			else:
				found = wanted in _match_key(f"{item.get('label') or ''} {item.get('id') or ''}")
			if wanted and found and value and not PLACEHOLDER_VALUE.match(value):
				cells[name] = value[:MAX_CELL_LENGTH]
				break
	return cells


def _match_key(text) -> str:
	return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def import_rows(
	site: str,
	section: str,
	extraction_name: str,
	rows: list,
	seen_run=None,
	extra_cells: dict | None = None,
	mill_id: str = "",
) -> dict:
	"""Upsert a batch of scraped rows of one section.

	``rows`` items: {"cells": {...}, "details": [{...}, ...] | None, "details_footer": [{...}] | None,
	"receipt": {"filename", "content_b64", "source_url"} | None, "receipt_error": str | None,
	"detail_error": str | None, "documents": [{"label", "filename", "content_b64", "source_url", "error"}]}
	(``documents``: files of several document buttons per row, noted in the record's
	``documents``). ``details`` None means "not captured": existing
	detail rows are kept. ``row_no`` is the row's position on the portal; with
	``seen_run`` (start of the search) it keeps reports in portal order. ``details_footer`` holds the detail table's footer lines
	(e.g. "Total"), kept apart from the detail rows. Column order is kept as on
	the portal. ``extra_cells`` (e.g. the search's KMS Year and Depot) are put
	before the portal columns of every row. ``mill_id`` is the Mill No. picked on the
	form: the mill of every row (see row_mill_id). Returns counts and per-row errors.

	Portal data has priority: a row read from the portal replaces a row entered
	by hand (see portal_manual.py) with the same key.
	"""
	if len(rows) > MAX_ROWS_PER_CALL:
		frappe.throw(_("Send at most {0} rows per call").format(MAX_ROWS_PER_CALL))

	site_doc = frappe.get_cached_doc("Portal Site", site)
	section_row = site_doc.get_section(section)
	key_columns = parse_key_columns(section_row.key_columns if section_row else "")
	target = frappe._dict(
		site=site,
		section=section,
		name=extraction_name,
		seen_run=seen_run,
		extra_cells=extra_cells or {},
		mill_id=mill_id or "",
		mill_label_keys=mill_label_keys(site_doc.get("mill_id_labels")),
	)

	result = {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 0, "receipts": 0, "errors": [], "new_rows": []}
	for idx, row in enumerate(rows, start=1):
		row = row or {}
		save_point = f"portal_row_{idx}"
		frappe.db.savepoint(save_point)
		try:
			outcome, doc = _upsert_row(target, row, key_columns)
		except Exception as e:
			frappe.db.rollback(save_point=save_point)
			clear_last_message()
			result["failed"] += 1
			result["errors"].append(_("Row {0}: {1}").format(idx, _error_text(e)))
			continue
		frappe.db.release_savepoint(save_point)
		result[outcome] += 1
		if outcome == "inserted" and (label := new_row_label(site, section, doc)):
			result["new_rows"].append(label)

		# A bad receipt only adds a warning; the row data is already saved.
		receipt_error = row.get("receipt_error")
		if row.get("receipt"):
			frappe.db.savepoint(save_point)
			try:
				result["receipts"] += int(_save_receipt(doc, row["receipt"]))
			except Exception as e:
				frappe.db.rollback(save_point=save_point)
				clear_last_message()
				receipt_error = _error_text(e)
			else:
				frappe.db.release_savepoint(save_point)
		if receipt_error:
			result["errors"].append(_("Row {0}: receipt not saved: {1}").format(idx, receipt_error))

		# Several documents per row (e.g. DCRO DC Transit Challan: Details, AC Note Doc).
		for document in row.get("documents") or []:
			label = _squash((document or {}).get("label"))[:SUMMARY_LENGTH] or _("Document")
			error = (document or {}).get("error")
			if document and document.get("content_b64"):
				frappe.db.savepoint(save_point)
				try:
					result["receipts"] += int(_save_document(doc, label, document))
				except Exception as e:
					frappe.db.rollback(save_point=save_point)
					clear_last_message()
					error = _error_text(e)
				else:
					frappe.db.release_savepoint(save_point)
			if error:
				result["errors"].append(_("Row {0}: '{1}' not saved: {2}").format(idx, label, error))
		if row.get("detail_error"):
			result["errors"].append(_("Row {0}: details not read: {1}").format(idx, row["detail_error"]))
	return result


# Sections whose new rows are named in the "new rows" notification after a read
# (portal_data_extraction.finish_run): (site, section) -> columns that name the row.
NEW_ROW_LABELS = {
	("DCRO", "View DC"): ["DC Code(RRC)"],
	("DCRO", "DC Transit Challan"): ["DC Order No", "Lot No."],
	("SCMS", "Lot Search"): ["DC No.", "Lot No."],
}


def new_row_label(site: str, section: str, doc) -> str:
	"""Name of a new row for the notification, e.g. "DCF050231" or "DCF051889 / Lot 97". Every
	section is notified: one not in NEW_ROW_LABELS is named by its summary (e.g. Paddy Release
	"RO260500492"), else by its record name."""
	columns = NEW_ROW_LABELS.get((site, section))
	if not columns:
		return doc.get("summary") or doc.get("name") or _("(no number)")
	cells = _load_json(doc.row_data)
	values = [cells.get(column, "").strip() for column in columns]
	if len(values) > 1 and values[1]:
		values[1] = f"Lot {values[1]}"
	return " / ".join(value for value in values if value) or _("(no number)")


def _upsert_row(extraction, row: dict, key_columns: list[str]) -> tuple[str, Document]:
	cells = normalize_cells(row.get("cells"))
	if extraction.extra_cells:
		cells = {**normalize_cells(extraction.extra_cells), **cells}
	cells = fix_section_cells(extraction.section, cells)
	record_key = build_record_key(cells, key_columns)
	mill_id = row_mill_id(cells, extraction.mill_label_keys or mill_label_keys(None), extraction.mill_id)
	name = resolve_record_name(extraction.site, extraction.section, record_key, mill_id)
	# Added after the key: the Net Weight / Accepted Date / District never make a new record.
	cells = add_net_weight(extraction.site, extraction.section, cells, row, name)
	cells = add_dc_district(extraction.site, extraction.section, cells, row, name)
	cells = add_lot_vehicle(extraction.site, extraction.section, cells, row, name)
	row_hash = build_row_hash(cells)
	details = normalize_details(row["details"]) if row.get("details") is not None else None
	receipt = row.get("receipt") or None
	now = now_datetime()

	values = {
		"row_data": json.dumps(cells, ensure_ascii=False),
		"row_hash": row_hash,
		"summary": build_summary(cells, key_columns),
		"extraction": extraction.name,
		"last_seen_on": now,
		"seen_run": extraction.seen_run or now,
		"row_no": cint(row.get("row_no")),
		"entry_source": "Portal",
		"mill_id": mill_id,
		# Fingerprint from the agent: next time this row is skipped while unchanged.
		"portal_row_sig": _squash(row.get("row_sig"))[:20],
	}
	if receipt and receipt.get("source_url"):
		values["receipt_url"] = _squash(receipt["source_url"])[:MAX_CELL_LENGTH]
	if details is not None:
		footer = normalize_details(row.get("details_footer") or [])
		values["details_hash"] = build_details_hash(details + footer)
		values["detail_count"] = len(details)
		values["details_footer"] = json.dumps(footer, ensure_ascii=False)
		values["details_source"] = "Portal"

	if not frappe.db.exists("Portal Record", name):
		doc = frappe.new_doc("Portal Record")
		doc.name = name
		doc.update(
			{
				"site": extraction.site,
				"section": extraction.section,
				"record_key": record_key,
				"first_seen_on": now,
				**values,
			}
		)
		_set_details(doc, details)
		doc.insert(ignore_permissions=True)
		return "inserted", doc

	doc = frappe.get_doc("Portal Record", name)
	details_same = details is None or (
		doc.details_hash == values["details_hash"] and doc.details_source != "Manual"
	)
	# A row entered by hand is always replaced, even when the portal shows the same values.
	if doc.row_hash == row_hash and details_same and doc.entry_source != "Manual" and (doc.mill_id or "") == mill_id:
		# Only bookkeeping changed; do not bump `modified` or add a version.
		frappe.db.set_value(
			"Portal Record",
			name,
			{
				"extraction": extraction.name,
				"last_seen_on": now,
				"seen_run": values["seen_run"],
				"row_no": values["row_no"],
				"portal_row_sig": values["portal_row_sig"],
			},
			update_modified=False,
		)
		return "unchanged", doc

	doc.update(values)
	_set_details(doc, details)
	doc.save(ignore_permissions=True)
	return "updated", doc


def rekey_section(site: str, section: str):
	"""Re-key the saved records of a section after its Key Columns were set:
	one record per key; for a key saved more than once, the latest read is kept."""
	section_row = frappe.get_cached_doc("Portal Site", site).get_section(section)
	key_columns = parse_key_columns(section_row.key_columns if section_row else "")
	if not key_columns:
		return
	records = frappe.get_all(
		"Portal Record",
		filters={"site": site, "section": section},
		fields=["name", "row_data", "mill_id"],
		order_by="last_seen_on desc, seen_run desc",
	)
	kept = set()
	for record in records:
		cells = json.loads(record.row_data or "{}") or {}
		record_key = build_record_key(without_net_weight(site, section, cells), key_columns)
		new_name = build_record_name(site, section, record_key, record.mill_id or "")
		if new_name in kept:
			frappe.delete_doc("Portal Record", record.name, ignore_permissions=True, force=True)
			continue
		kept.add(new_name)
		if new_name != record.name:
			frappe.rename_doc("Portal Record", record.name, new_name, force=True, show_alert=False)
		frappe.db.set_value(
			"Portal Record",
			new_name,
			{
				"record_key": record_key,
				"summary": build_summary(cells, key_columns),
				"row_hash": build_row_hash(cells),
			},
			update_modified=False,
		)


def _set_details(doc, details: list[dict[str, str]] | None):
	if details is None:
		return
	doc.set(
		"details",
		[
			{
				"line_no": idx,
				"summary": " · ".join(v for v in meaningful_cells(cells).values() if v)[:SUMMARY_LENGTH],
				"detail_data": json.dumps(cells, ensure_ascii=False),
			}
			for idx, cells in enumerate(details, start=1)
		],
	)


def _save_receipt(doc, receipt: dict | None) -> bool:
	"""Attach a receipt PDF as a private file. Skips it when the same file is already attached."""
	if not receipt or not receipt.get("content_b64"):
		return False

	try:
		content = base64.b64decode(receipt["content_b64"], validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("Receipt file is not valid base64"))
	if len(content) > MAX_RECEIPT_BYTES:
		frappe.throw(_("Receipt is larger than {0} MB").format(MAX_RECEIPT_BYTES // (1024 * 1024)))
	if not content.startswith(b"%PDF"):
		frappe.throw(_("Receipt is not a PDF file"))

	if doc.receipt_file:
		old_hash = frappe.db.get_value("File", {"file_url": doc.receipt_file}, "content_hash")
		if old_hash and old_hash == get_content_hash(content):
			return False

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			# Named after the record (e.g. "Transit_Challan_RRC_TC_123_L_9.pdf"), not the agent's temp name.
			"file_name": _safe_pdf_name(f"{doc.section}_{doc.summary}" if doc.summary else receipt.get("filename"), doc.name),
			"attached_to_doctype": "Portal Record",
			"attached_to_name": doc.name,
			"attached_to_field": "receipt_file",
			"is_private": 1,
			"content": content,
		}
	)
	file_doc.save(ignore_permissions=True)
	frappe.db.set_value("Portal Record", doc.name, "receipt_file", file_doc.file_url, update_modified=False)
	doc.receipt_file = file_doc.file_url
	return True


def _save_document(doc, label: str, document: dict) -> bool:
	"""Attach one of the row's documents (PDF or image) and note it in ``documents``
	({label: file url}). Skips it when the same file is already saved for that label."""
	content, ext = _decode_file(document["content_b64"])
	saved = _load_json(doc.documents)
	old_url = saved.get(label)
	if old_url:
		old_hash = frappe.db.get_value("File", {"file_url": old_url}, "content_hash")
		if old_hash and old_hash == get_content_hash(content):
			return False

	stem = _safe_pdf_name(f"{doc.section}_{doc.summary}_{label}", doc.name)[: -len(".pdf")]
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{stem}{ext}",
			"attached_to_doctype": "Portal Record",
			"attached_to_name": doc.name,
			"is_private": 1,
			"content": content,
		}
	)
	file_doc.save(ignore_permissions=True)
	saved[label] = file_doc.file_url
	doc.documents = json.dumps(saved, ensure_ascii=False)
	frappe.db.set_value("Portal Record", doc.name, "documents", doc.documents, update_modified=False)
	return True


# Files kept from a portal document button, by their first bytes.
FILE_KINDS = ((b"%PDF", ".pdf"), (b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"))


def _decode_file(content_b64: str) -> tuple[bytes, str]:
	try:
		content = base64.b64decode(content_b64, validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("File is not valid base64"))
	if len(content) > MAX_RECEIPT_BYTES:
		frappe.throw(_("File is larger than {0} MB").format(MAX_RECEIPT_BYTES // (1024 * 1024)))
	for magic, ext in FILE_KINDS:
		if content.startswith(magic):
			return content, ext
	frappe.throw(_("File is not a PDF or image"))


def _load_json(raw) -> dict:
	try:
		value = json.loads(raw or "{}")
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


def _safe_pdf_name(filename: str | None, fallback: str) -> str:
	stem = re.sub(r"\.pdf$", "", (filename or "").strip(), flags=re.IGNORECASE)
	stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")[:80]
	return f"{stem or fallback}.pdf"


def append_log(extraction, message: str):
	line = f"[{now_datetime().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
	log = ((extraction.extraction_log or "") + "\n" + line).strip()
	if len(log) > MAX_LOG_LENGTH:
		log = log[-MAX_LOG_LENGTH:]
	extraction.extraction_log = log


def _error_text(e: Exception) -> str:
	return _squash(str(e)) or type(e).__name__


def _squash(value) -> str:
	if value is None:
		return ""
	return re.sub(r"\s+", " ", str(value)).strip()
