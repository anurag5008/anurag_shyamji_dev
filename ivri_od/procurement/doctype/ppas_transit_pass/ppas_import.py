# Copyright (c) 2026, Profezzo and contributors

import base64
import json
import re
from datetime import datetime
from io import BytesIO

import frappe
import openpyxl
from frappe import _
from frappe.utils import cint, cstr, flt
from frappe.utils.file_manager import save_file

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import (
	make_pass_unique_key,
)
from ivri_od.procurement.doctype.ppas_transit_pass.ppas_field_mapping import (
	STANDARD_EXCEL_COLUMNS,
)


BAG_COLUMN_KEYS = [
	"Bag",
	"Bags",
	"bag",
	"bags",
	"No. of Bag",
	"No of Bag",
	"No.Of Bag",
	"NoOfBag",
	"no_of_bag",
	"no_of_bags",
	"noofbag",
	"Number of Bag",
	"Number of Bags",
]

DELAY_COLUMN_KEYS = [
	"Delay(In Days)",
	"Delay (In Days)",
	"Delay In Days",
	"Delay Days",
	"delay_in_days",
	"delayindays",
	"delaydate",
	"DelayDate",
	"Delay Date",
]

MONTHS = {
	"jan": "01",
	"feb": "02",
	"mar": "03",
	"apr": "04",
	"may": "05",
	"jun": "06",
	"jul": "07",
	"aug": "08",
	"sep": "09",
	"oct": "10",
	"nov": "11",
	"dec": "12",
}


def _text(value):
	if value is None:
		return ""
	return cstr(value).strip()


def _number(value):
	if value is None or value == "":
		return 0
	try:
		return float(cstr(value).replace(",", "").strip())
	except (TypeError, ValueError):
		return 0


def get_row_value(row, keys):
	if not isinstance(row, dict):
		return None

	for key in keys:
		if key in row and row[key] is not None and cstr(row[key]).strip() != "":
			return row[key]

	normalized_keys = {re.sub(r"[^a-z0-9]", "", k.lower()) for k in keys}
	for actual_key, value in row.items():
		if value is None or cstr(value).strip() == "":
			continue
		actual = re.sub(r"[^a-z0-9]", "", cstr(actual_key).lower())
		if actual in normalized_keys:
			return value

	return None


def split_datetime(value):
	if value is None or cstr(value).strip() == "":
		return None, None

	raw = cstr(value).strip()

	ppas_match = re.match(
		r"^(\d{2})-([A-Za-z]{3})-(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?",
		raw,
	)
	if ppas_match:
		month_key = ppas_match.group(2).lower()
		month = MONTHS.get(month_key)
		if month:
			date_value = f"{ppas_match.group(3)}-{month}-{ppas_match.group(1)}"
			time_value = f"{ppas_match.group(4)}:{ppas_match.group(5)}:{ppas_match.group(6) or '00'}"
			return date_value, time_value

	iso_match = re.match(
		r"^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2}))?",
		raw,
	)
	if iso_match:
		date_value = f"{iso_match.group(1)}-{iso_match.group(2)}-{iso_match.group(3)}"
		time_value = f"{iso_match.group(4)}:{iso_match.group(5)}:{iso_match.group(6) or '00'}"
		return date_value, time_value

	if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
		return raw, None

	date_only = re.match(r"^(\d{2})-([A-Za-z]{3})-(\d{4})$", raw)
	if date_only:
		month_key = date_only.group(2).lower()
		month = MONTHS.get(month_key)
		if month:
			return f"{date_only.group(3)}-{month}-{date_only.group(1)}", None

	return None, None


def normalize_date_only(value):
	if value is None or cstr(value).strip() == "":
		return None

	date_value, _time_value = split_datetime(value)
	return date_value


def normalize_time_only(value):
	if value is None or cstr(value).strip() == "":
		return None

	raw = cstr(value).strip()
	time_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", raw)
	if time_match:
		return f"{time_match.group(1).zfill(2)}:{time_match.group(2)}:{time_match.group(3) or '00'}"

	_date_value, time_value = split_datetime(value)
	return time_value


def normalize_ppas_excel_row(row):
	"""Normalize one Excel/scrape row to standard column names (4 date/time columns)."""
	transit_date = normalize_date_only(
		get_row_value(
			row,
			[
				"Transit Pass Date",
				"transit_pass_date",
				"TransitPassDate",
				"trasistpassdate",
			],
		)
	)
	transit_time = normalize_time_only(
		get_row_value(
			row,
			[
				"Transit Pass Time",
				"transit_pass_time",
				"TransitPassTime",
				"trasistpasstime",
			],
		)
	)

	if not transit_time:
		split_date, split_time = split_datetime(
			get_row_value(row, ["Transit Pass Date", "transit_pass_date"])
		)
		transit_date = transit_date or split_date
		transit_time = split_time

	accepted_date = normalize_date_only(
		get_row_value(
			row,
			[
				"Accepted Date",
				"accepted_date",
				"AcceptedDate",
				"accptedate",
				"acceptedate",
			],
		)
	)
	accepted_time = normalize_time_only(
		get_row_value(
			row,
			[
				"Accepted Time",
				"accepted_time",
				"AcceptedTime",
				"accppetedtime",
				"acceptedtime",
			],
		)
	)

	if not accepted_time:
		split_date, split_time = split_datetime(
			get_row_value(row, ["Accepted Date", "accepted_date"])
		)
		accepted_date = accepted_date or split_date
		accepted_time = split_time

	return {
		"Sl#": cint(_number(get_row_value(row, ["Sl#", "Sl", "sl"]))),
		"PACS": _text(get_row_value(row, ["PACS", "pacs"])),
		"PPC": _text(get_row_value(row, ["PPC", "ppc", "Ppc", "P.P.C"])),
		"Miller": _text(get_row_value(row, ["Miller", "miller"])),
		"Transit Pass No.": _text(
			get_row_value(
				row,
				[
					"Transit Pass No.",
					"Transit Pass No",
					"TransitPassNo",
					"transit_pass_no",
					"TP No",
					"TP No.",
				],
			)
		),
		"Vehicle No": _text(get_row_value(row, ["Vehicle No", "Vehicle No.", "vehicle_no"])),
		"Driver Name": _text(get_row_value(row, ["Driver Name", "driver_name"])),
		"Bag": cint(
			_number(
				get_row_value(
					row,
					BAG_COLUMN_KEYS,
				)
			)
		),
		"Quantity": flt(_number(get_row_value(row, ["Quantity", "quantity"]))),
		"Transit Pass Date": transit_date,
		"Transit Pass Time": transit_time,
		"Delay(In Days)": cint(
			round(
				_number(
					get_row_value(
						row,
						DELAY_COLUMN_KEYS,
					)
				)
			)
		),
		"Accepted Date": accepted_date,
		"Accepted Time": accepted_time,
		"Action": _text(get_row_value(row, ["Action", "action"])),
	}


def standardize_ppas_rows(rows):
	if not isinstance(rows, list):
		return []
	return [normalize_ppas_excel_row(row) for row in rows]


def build_standard_ppas_excel(rows):
	"""Build Excel with separate Transit Pass / Accepted date & time columns."""
	workbook = openpyxl.Workbook()
	worksheet = workbook.active
	worksheet.title = "PPAS Transit Pass"
	worksheet.append(STANDARD_EXCEL_COLUMNS)

	for row in rows:
		worksheet.append([row.get(column) for column in STANDARD_EXCEL_COLUMNS])

	buffer = BytesIO()
	workbook.save(buffer)
	return base64.b64encode(buffer.getvalue()).decode()


def parse_season_meta(season):
	season_text = _text(season)
	season_lower = season_text.lower()

	crop_season = ""
	if "kharif" in season_lower:
		crop_season = "Kharif"
	elif "rabi" in season_lower:
		crop_season = "Rabi"

	year_match = re.search(r"(\d{4})", season_text)
	season_year = cint(year_match.group(1)) if year_match else datetime.now().year

	if crop_season == "Kharif":
		naming_series = "KH-.YYYY.-.######"
	elif crop_season == "Rabi":
		naming_series = "RA-.YYYY.-.######"
	else:
		naming_series = "PP-.YYYY.-.######"

	return crop_season, season_year, naming_series


def row_identity_key(season, ppc, transit_pass_no):
	return "|".join(
		[
			_text(season).upper(),
			_text(ppc).upper(),
			_text(transit_pass_no).upper(),
		]
	)


def _int_from_std_or_row(std, row, std_key, doctype_fieldnames, column_keys):
	value = std.get(std_key)
	if value is not None and cstr(value).strip() != "":
		return cint(_number(value))

	for fieldname in doctype_fieldnames:
		raw = row.get(fieldname) if isinstance(row, dict) else None
		if raw is not None and cstr(raw).strip() != "":
			return cint(_number(raw))

	fallback = get_row_value(row, column_keys) if isinstance(row, dict) else None
	if fallback is not None and cstr(fallback).strip() != "":
		return cint(_number(fallback))

	return 0


def _rows_have_positive_values(rows, std_key):
	if not rows:
		return False

	sample = rows[: min(10, len(rows))]
	for row in sample:
		std = normalize_ppas_excel_row(row)
		if _int_from_std_or_row(std, row, std_key, [], []) > 0:
			return True

	return False


def _enrich_rows_with_excel(primary_rows, excel_rows):
	"""Fill missing Bag / Delay from parsed Excel when agent JSON omits them."""
	if not primary_rows:
		return excel_rows or []
	if not excel_rows:
		return primary_rows

	excel_index = {}
	for excel_row in excel_rows:
		std = normalize_ppas_excel_row(excel_row)
		tp_no = _text(std.get("Transit Pass No.")).upper()
		ppc = _text(std.get("PPC")).upper()
		if tp_no:
			excel_index[(ppc, tp_no)] = std

	enriched = []
	for row in primary_rows:
		merged = dict(row) if isinstance(row, dict) else {}
		std = normalize_ppas_excel_row(merged)
		tp_no = _text(std.get("Transit Pass No.")).upper()
		ppc = _text(std.get("PPC")).upper()
		excel_std = excel_index.get((ppc, tp_no)) if tp_no else None

		if excel_std:
			if _int_from_std_or_row(std, merged, "Bag", ["bags"], BAG_COLUMN_KEYS) == 0:
				bag_value = excel_std.get("Bag")
				if bag_value is not None and cstr(bag_value).strip() != "":
					merged["Bag"] = bag_value

			if _int_from_std_or_row(std, merged, "Delay(In Days)", ["delay_in_days"], DELAY_COLUMN_KEYS) == 0:
				delay_value = excel_std.get("Delay(In Days)")
				if delay_value is not None and cstr(delay_value).strip() != "":
					merged["Delay(In Days)"] = delay_value

		enriched.append(merged)

	return enriched


def _resolve_import_rows(scraped_rows, file_rows):
	scraped_rows = scraped_rows or []
	file_rows = file_rows or []

	if not scraped_rows:
		return file_rows
	if not file_rows:
		return scraped_rows

	file_has_bags = _rows_have_positive_values(file_rows, "Bag")
	scraped_has_bags = _rows_have_positive_values(scraped_rows, "Bag")

	if file_has_bags and not scraped_has_bags:
		return file_rows

	rows = scraped_rows
	if file_rows:
		rows = _enrich_rows_with_excel(scraped_rows, file_rows)

	return rows


def map_ppas_row(row, season):
	std = normalize_ppas_excel_row(row)

	return {
		"season": _text(season),
		"sl": std.get("Sl#"),
		"pacs": _text(std.get("PACS")),
		"ppc": _text(std.get("PPC")),
		"miller": _text(std.get("Miller")),
		"transit_pass_no": _text(std.get("Transit Pass No.")),
		"transit_pass_date": std.get("Transit Pass Date"),
		"transit_pass_time": std.get("Transit Pass Time"),
		"vehicle_no": _text(std.get("Vehicle No")),
		"driver_name": _text(std.get("Driver Name")),
		"bags": _int_from_std_or_row(std, row, "Bag", ["bags"], BAG_COLUMN_KEYS),
		"quantity": flt(_number(std.get("Quantity"))),
		"delay_in_days": _int_from_std_or_row(
			std, row, "Delay(In Days)", ["delay_in_days"], DELAY_COLUMN_KEYS
		),
		"accepted_date": std.get("Accepted Date"),
		"accepted_time": std.get("Accepted Time"),
		"action": _text(std.get("Action")),
	}


def _ensure_identity_fields(data):
	"""Fill required identity fields so Frappe can always save a row."""
	if not data.get("ppc"):
		data["ppc"] = data.get("pacs") or "UNKNOWN"

	if not data.get("transit_pass_no"):
		sl = data.get("sl")
		if sl:
			data["transit_pass_no"] = f"SL-{sl}"
		else:
			data["transit_pass_no"] = frappe.generate_hash(length=10)

	data["pass_unique_key"] = make_pass_unique_key(
		data.get("transit_pass_no"),
		data.get("ppc"),
		data.get("miller"),
		data.get("season"),
	)

	return data


def _nullify_blanks(data):
	for fieldname, value in list(data.items()):
		if value == "":
			data[fieldname] = None
	return data


def _save_ppas_transit_pass(data, existing_name=None):
	data = _nullify_blanks(_ensure_identity_fields(dict(data)))

	if existing_name:
		doc = frappe.get_doc("PPAS Transit Pass", existing_name)
		doc.update(data)
		doc.bags = cint(data.get("bags") or 0)
		doc.delay_in_days = cint(data.get("delay_in_days") or 0)
		doc.save(ignore_permissions=True)
		return doc.name

	doc = frappe.new_doc("PPAS Transit Pass")
	doc.update(data)
	doc.bags = cint(data.get("bags") or 0)
	doc.delay_in_days = cint(data.get("delay_in_days") or 0)
	doc.insert(ignore_permissions=True)
	return doc.name


def _remove_old_ppas_excel_files(extraction_name):
	for file_name in frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "PPAS Data Extraction",
			"attached_to_name": extraction_name,
		},
		pluck="name",
	):
		frappe.delete_doc("File", file_name, ignore_permissions=True)


def attach_standard_ppas_excel(extraction_name, season, rows):
	"""Write a valid .xlsx (binary) and attach to PPAS Data Extraction."""
	standard_rows = standardize_ppas_rows(rows or [])
	filename = f"PPAS_Transit_Pass_{cstr(season).replace('(', '_').replace(')', '')}_standard.xlsx"
	excel_bytes = base64.b64decode(build_standard_ppas_excel(standard_rows))

	_remove_old_ppas_excel_files(extraction_name)
	file_doc = save_file(
		filename,
		excel_bytes,
		"PPAS Data Extraction",
		extraction_name,
		is_private=0,
	)

	return {
		"rows": standard_rows,
		"filename": filename,
		"download_url": file_doc.file_url,
		"record_count": len(standard_rows),
	}


@frappe.whitelist()
def prepare_ppas_import(extraction_name, season, rows):
	if isinstance(rows, str):
		rows = json.loads(rows)
	return attach_standard_ppas_excel(extraction_name, season, rows or [])


def _load_rows(rows, rows_json=None):
	if rows_json:
		rows = json.loads(rows_json)
	if isinstance(rows, str):
		rows = json.loads(rows)
	if not isinstance(rows, list):
		frappe.throw(_("PPAS rows must be a list"))
	return rows


def bulk_import_from_ppas(season, rows=None, rows_json=None):
	"""Import PPAS rows into PPAS Transit Pass (server-side)."""
	if not season:
		frappe.throw(_("Season is required"))

	rows = _load_rows(rows, rows_json)
	if not rows:
		frappe.throw(_("No PPAS rows to import"))

	standard_rows = standardize_ppas_rows(rows)

	existing_records = frappe.get_all(
		"PPAS Transit Pass",
		filters={"season": season},
		fields=["name", "season", "ppc", "transit_pass_no"],
		limit_page_length=0,
	)

	existing_map = {
		row_identity_key(record.season, record.ppc, record.transit_pass_no): record.name
		for record in existing_records
	}

	imported = 0
	updated = 0
	failed = 0
	errors = []

	for index, row in enumerate(standard_rows, start=1):
		try:
			data = _ensure_identity_fields(map_ppas_row(row, season))
			key = row_identity_key(season, data["ppc"], data["transit_pass_no"])
			existing_name = existing_map.get(key)

			doc_name = _save_ppas_transit_pass(data, existing_name=existing_name)

			if existing_name:
				updated += 1
			else:
				imported += 1
				existing_map[key] = doc_name

			if index % 25 == 0:
				frappe.db.commit()

		except Exception as exc:
			failed += 1
			errors.append({"row": index, "error": cstr(exc)})
			frappe.log_error(
				title="PPAS Transit Pass import row failed",
				message=frappe.get_traceback(),
			)

	frappe.db.commit()

	return {
		"success": (imported + updated) > 0,
		"total": len(standard_rows),
		"imported": imported,
		"updated": updated,
		"failed": failed,
		"errors": errors[:20],
	}


@frappe.whitelist()
def bulk_import_from_ppas_api(season, rows=None, rows_json=None):
	return bulk_import_from_ppas(season, rows=rows, rows_json=rows_json)


@frappe.whitelist()
def run_ppas_extraction_import(extraction_name, season, rows_json=None, file_content=None):
	"""Parse Excel, attach a valid .xlsx, and save all rows into PPAS Transit Pass."""
	if not extraction_name:
		frappe.throw(_("Save PPAS Data Extraction before importing."))

	if not season:
		frappe.throw(_("Season is required"))

	scraped_rows = _load_rows(None, rows_json) if rows_json else []
	file_rows = []

	if file_content:
		from ivri_od.procurement.doctype.ppas_data_extraction.ppas_data_extraction import (
			parse_ppas_excel_file,
		)

		file_rows = parse_ppas_excel_file(file_content)

	rows = _resolve_import_rows(scraped_rows, file_rows)

	if not rows:
		frappe.throw(_("No PPAS rows to import"))

	file_info = {}
	try:
		file_info = attach_standard_ppas_excel(extraction_name, season, rows)
	except Exception as exc:
		frappe.log_error(
			title="PPAS standard Excel attachment failed",
			message=frappe.get_traceback(),
		)
		file_info = {"attachment_error": cstr(exc)}

	standard_rows = file_info.get("rows") if isinstance(file_info, dict) else None
	import_result = bulk_import_from_ppas(season, rows=standard_rows or rows)

	return {
		**file_info,
		**import_result,
	}


# --- Manual copy/paste import (PPAS Transit Pass Import) ---

_PASTE_HEADER_CANONICAL = {
	"season": "Season",
	"sl": "Sl#",
	"slno": "Sl#",
	"pacs": "PACS",
	"ppc": "PPC",
	"miller": "Miller",
	"transitpassno": "Transit Pass No.",
	"transitpassdate": "Transit Pass Date",
	"vehicleno": "Vehicle No",
	"drivername": "Driver Name",
	"bag": "Bag",
	"bags": "Bag",
	"quantity": "Quantity",
	"delayindays": "Delay(In Days)",
	"accepteddate": "Accepted Date",
	"action": "Action",
}


def _normalize_header_key(header):
	return re.sub(r"[^a-z0-9]", "", cstr(header).lower())


def _looks_like_paste_header(cells):
	if not cells:
		return False
	keys = {_normalize_header_key(cell) for cell in cells if cstr(cell).strip()}
	if "transitpassno" in keys or "sl" in keys or "slno" in keys:
		return True
	joined = " ".join(cstr(c).lower() for c in cells)
	return "transit pass" in joined


def _canonical_paste_header(header):
	key = _normalize_header_key(header)
	return _PASTE_HEADER_CANONICAL.get(key, _text(header))


def _row_dict_from_fixed_columns(cells):
	"""Map tab-separated cells when no header row is present."""
	cells = [cstr(c).strip() for c in cells]
	n = len(cells)
	if n < 10:
		return {}

	offset = 0
	first = cells[0].lower() if cells else ""
	if n >= 14 and ("kharif" in first or "rabi" in first or "(" in first):
		offset = 1

	def at(index):
		pos = offset + index
		return cells[pos] if pos < n else ""

	row = {
		"Season": cells[0] if offset else "",
		"Sl#": at(0),
		"PACS": at(1),
		"PPC": at(2),
		"Miller": at(3),
		"Transit Pass No.": at(4),
		"Transit Pass Date": at(5),
		"Vehicle No": at(6),
		"Driver Name": at(7),
		"Bag": at(8),
		"Quantity": at(9),
		"Delay(In Days)": at(10) if n > offset + 10 else "",
		"Accepted Date": at(11) if n > offset + 11 else "",
		"Action": at(12) if n > offset + 12 else "",
	}
	return row


def parse_ppas_tab_paste(paste_data):
	"""Parse tab-separated PPAS portal / Excel clipboard text into row dicts."""
	raw_text = cstr(paste_data or "").replace("\r\n", "\n").replace("\r", "\n")
	lines = [line for line in raw_text.split("\n") if cstr(line).strip()]
	if not lines:
		return []

	rows = []
	header_labels = None

	for line in lines:
		cells = line.split("\t")
		if header_labels is None and _looks_like_paste_header(cells):
			header_labels = [_canonical_paste_header(cell) for cell in cells]
			continue

		if header_labels:
			row = {}
			for index, label in enumerate(header_labels):
				row[label] = cstr(cells[index]).strip() if index < len(cells) else ""
			if any(cstr(v).strip() for v in row.values()):
				rows.append(row)
		else:
			row = _row_dict_from_fixed_columns(cells)
			if row and any(cstr(v).strip() for v in row.values()):
				rows.append(row)

	return rows


def resolve_ppas_season_text(season):
	"""PPAS Transit Pass season text (e.g. Kharif(2025)) from Season Master or raw text."""
	season_text = _text(season)
	if not season_text:
		return ""

	if frappe.db.exists("Season Master", season_text):
		doc = frappe.get_cached_doc("Season Master", season_text)
		if doc.crop_season and doc.year:
			return f"{doc.crop_season}({doc.year})"

	if re.search(r"\(\d{4}\)", season_text):
		return season_text

	parts = season_text.replace("(", " ").replace(")", " ").split()
	if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) == 4:
		return f"{parts[0]}({parts[-1]})"

	return season_text


def validate_manual_ppas_std_row(std):
	errors = []
	tp_no = _text(std.get("Transit Pass No."))
	ppc = _text(std.get("PPC"))
	vehicle = _text(std.get("Vehicle No"))
	tp_date = std.get("Transit Pass Date")
	quantity = flt(_number(std.get("Quantity")))
	bags = cint(_number(std.get("Bag")))

	if not tp_no:
		errors.append(_("Transit Pass No is required"))
	if not ppc:
		errors.append(_("PPC is required"))
	if not vehicle:
		errors.append(_("Vehicle No is required"))
	if not tp_date:
		errors.append(_("Transit Pass Date is required"))
	if quantity <= 0:
		errors.append(_("Quantity must be numeric and greater than 0"))
	if bags < 0:
		errors.append(_("Bags must not be negative"))

	return errors


def _manual_item_from_std(std, season_text, row_status, error_message=""):
	return {
		"source_sl": cint(std.get("Sl#")),
		"season": season_text,
		"pacs": _text(std.get("PACS")),
		"ppc": _text(std.get("PPC")),
		"miller": _text(std.get("Miller")),
		"transit_pass_no": _text(std.get("Transit Pass No.")),
		"transit_pass_date": std.get("Transit Pass Date"),
		"transit_pass_time": std.get("Transit Pass Time"),
		"vehicle_no": _text(std.get("Vehicle No")),
		"driver_name": _text(std.get("Driver Name")),
		"bag": cint(_number(std.get("Bag"))),
		"quantity": flt(_number(std.get("Quantity"))),
		"delay_in_days": cint(_number(std.get("Delay(In Days)"))),
		"accepted_date": std.get("Accepted Date"),
		"accepted_time": std.get("Accepted Time"),
		"action": _text(std.get("Action")),
		"row_status": row_status,
		"error_message": error_message,
	}


def _iso_date_value(value):
	"""Normalize any date-like value to YYYY-MM-DD for PPAS Transit Pass."""
	if value is None or cstr(value).strip() == "":
		return None

	from datetime import date, datetime

	from frappe.utils import getdate

	if isinstance(value, (date, datetime)):
		return getdate(value).isoformat()

	raw = cstr(value).strip()
	if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
		return raw

	parsed_date, _parsed_time = split_datetime(raw)
	if parsed_date:
		return parsed_date

	try:
		return getdate(raw).isoformat()
	except Exception:
		return None


def _iso_time_value(value):
	"""Normalize time-like values to HH:MM:SS for PPAS Transit Pass."""
	if value is None or cstr(value).strip() == "":
		return None

	from datetime import time, timedelta

	from frappe.utils import get_time

	if isinstance(value, timedelta):
		total_seconds = int(value.total_seconds()) % 86400
		hours, remainder = divmod(total_seconds, 3600)
		minutes, seconds = divmod(remainder, 60)
		return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

	if isinstance(value, time):
		return value.strftime("%H:%M:%S")

	raw = cstr(value).strip()
	_parsed_date, parsed_time = split_datetime(raw)
	if parsed_time:
		return parsed_time

	try:
		return get_time(raw).strftime("%H:%M:%S")
	except Exception:
		time_match = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", raw)
		if time_match:
			return f"{time_match.group(1).zfill(2)}:{time_match.group(2)}:{time_match.group(3) or '00'}"
	return None


def _serialize_import_field_value(value, field_kind="date"):
	if field_kind == "time":
		return _iso_time_value(value)
	return _iso_date_value(value)


def manual_item_from_import_child(row):
	"""JSON-safe import row from PPAS Transit Pass Import Item (no DocType metadata)."""
	get = row.get if isinstance(row, dict) else lambda field: getattr(row, field, None)
	return {
		"source_sl": cint(get("source_sl")),
		"season": _text(get("season")),
		"pacs": _text(get("pacs")),
		"ppc": _text(get("ppc")),
		"miller": _text(get("miller")),
		"transit_pass_no": _text(get("transit_pass_no")),
		"transit_pass_date": _serialize_import_field_value(get("transit_pass_date"), "date"),
		"transit_pass_time": _serialize_import_field_value(get("transit_pass_time"), "time"),
		"vehicle_no": _text(get("vehicle_no")),
		"driver_name": _text(get("driver_name")),
		"bag": cint(get("bag") or 0),
		"quantity": flt(get("quantity") or 0),
		"delay_in_days": cint(get("delay_in_days") or 0),
		"accepted_date": _serialize_import_field_value(get("accepted_date"), "date"),
		"accepted_time": _serialize_import_field_value(get("accepted_time"), "time"),
		"action": _text(get("action")),
		"row_status": _text(get("row_status")),
		"error_message": _text(get("error_message")),
	}


def map_manual_item_to_ppas_data(payload, season_text):
	"""Map saved import child row directly to PPAS Transit Pass fields (preserves dates)."""
	return {
		"season": season_text,
		"sl": cint(payload.get("source_sl")),
		"pacs": _text(payload.get("pacs")),
		"ppc": _text(payload.get("ppc")),
		"miller": _text(payload.get("miller")),
		"transit_pass_no": _text(payload.get("transit_pass_no")),
		"transit_pass_date": _iso_date_value(payload.get("transit_pass_date")),
		"transit_pass_time": _iso_time_value(payload.get("transit_pass_time")),
		"vehicle_no": _text(payload.get("vehicle_no")),
		"driver_name": _text(payload.get("driver_name")),
		"bags": cint(payload.get("bag") or 0),
		"quantity": flt(payload.get("quantity") or 0),
		"delay_in_days": cint(payload.get("delay_in_days") or 0),
		"accepted_date": _iso_date_value(payload.get("accepted_date")),
		"accepted_time": _iso_time_value(payload.get("accepted_time")),
		"action": _text(payload.get("action")),
	}


def _std_row_from_manual_item(item):
	if isinstance(item, str):
		item = json.loads(item)
	payload = manual_item_from_import_child(item)
	return {
		"Sl#": payload.get("source_sl"),
		"PACS": payload.get("pacs"),
		"PPC": payload.get("ppc"),
		"Miller": payload.get("miller"),
		"Transit Pass No.": payload.get("transit_pass_no"),
		"Transit Pass Date": payload.get("transit_pass_date"),
		"Transit Pass Time": payload.get("transit_pass_time"),
		"Vehicle No": payload.get("vehicle_no"),
		"Driver Name": payload.get("driver_name"),
		"Bag": payload.get("bag"),
		"Quantity": payload.get("quantity"),
		"Delay(In Days)": payload.get("delay_in_days"),
		"Accepted Date": payload.get("accepted_date"),
		"Accepted Time": payload.get("accepted_time"),
		"Action": payload.get("action"),
	}


def process_manual_ppas_paste(season, paste_data, miller=None):
	"""Parse and validate pasted PPAS rows without requiring a saved import document."""
	season_text = resolve_ppas_season_text(season)
	if not season_text:
		frappe.throw(_("Season is required"))

	paste_rows = parse_ppas_tab_paste(paste_data)
	if not paste_rows:
		frappe.throw(_("No PPAS rows found in pasted data"))

	existing_records = frappe.get_all(
		"PPAS Transit Pass",
		filters={"season": season_text},
		fields=["season", "ppc", "transit_pass_no"],
		limit_page_length=0,
	)
	existing_keys = {
		row_identity_key(record.season, record.ppc, record.transit_pass_no) for record in existing_records
	}

	seen_in_paste = set()
	items = []
	total = 0
	duplicate_count = 0
	failed_count = 0

	default_miller = _text(miller)

	for raw_row in paste_rows:
		if isinstance(raw_row, dict) and not _text(raw_row.get("Miller")) and default_miller:
			raw_row = dict(raw_row)
			raw_row["Miller"] = default_miller

		std_row = normalize_ppas_excel_row(raw_row)

		errors = validate_manual_ppas_std_row(std_row)
		ppc = _text(std_row.get("PPC"))
		tp_no = _text(std_row.get("Transit Pass No."))
		identity = row_identity_key(season_text, ppc, tp_no) if ppc and tp_no else ""

		if errors:
			row_status = "Failed"
			error_message = "; ".join(errors)
			failed_count += 1
		elif identity and identity in seen_in_paste:
			row_status = "Duplicate"
			error_message = _("Duplicate within pasted data")
			duplicate_count += 1
		elif identity and identity in existing_keys:
			row_status = "Duplicate"
			error_message = _("Already exists in ERP")
			duplicate_count += 1
		else:
			row_status = "Valid"
			error_message = ""
			if identity:
				seen_in_paste.add(identity)

		total += 1
		items.append(_manual_item_from_std(std_row, season_text, row_status, error_message))

	return {
		"season": season_text,
		"items": items,
		"total_records": total,
		"duplicate_records": duplicate_count,
		"failed_records": failed_count,
	}


@frappe.whitelist()
def process_manual_ppas_paste_api(season, paste_data, miller=None):
	return process_manual_ppas_paste(season, paste_data, miller=miller)


@frappe.whitelist()
def import_manual_ppas_valid_rows(season, items_json=None):
	"""Import only Valid rows from manual paste review into PPAS Transit Pass."""
	season_text = resolve_ppas_season_text(season)
	if not season_text:
		frappe.throw(_("Season is required"))

	if isinstance(items_json, str):
		items = json.loads(items_json)
	elif isinstance(items_json, list):
		items = items_json
	else:
		items = []

	valid_payloads = []
	for item in items:
		payload = manual_item_from_import_child(item)
		status = _text(payload.get("row_status"))
		if status and status != "Valid":
			continue
		valid_payloads.append(payload)

	if not valid_payloads:
		frappe.throw(_("No valid rows to import"))

	existing_records = frappe.get_all(
		"PPAS Transit Pass",
		filters={"season": season_text},
		fields=["name", "season", "ppc", "transit_pass_no"],
		limit_page_length=0,
	)
	existing_map = {
		row_identity_key(record.season, record.ppc, record.transit_pass_no): record.name
		for record in existing_records
	}

	imported = 0
	updated = 0
	failed = 0
	errors = []

	for index, payload in enumerate(valid_payloads, start=1):
		try:
			data = _ensure_identity_fields(map_manual_item_to_ppas_data(payload, season_text))
			key = row_identity_key(season_text, data["ppc"], data["transit_pass_no"])
			existing_name = existing_map.get(key)
			doc_name = _save_ppas_transit_pass(data, existing_name=existing_name)
			if existing_name:
				updated += 1
			else:
				imported += 1
				existing_map[key] = doc_name
			if index % 25 == 0:
				frappe.db.commit()
		except Exception as exc:
			failed += 1
			errors.append({"row": index, "error": cstr(exc)})

	frappe.db.commit()

	return {
		"success": (imported + updated) > 0,
		"total": len(valid_payloads),
		"imported": imported,
		"updated": updated,
		"failed": failed,
		"errors": errors[:20],
	}
