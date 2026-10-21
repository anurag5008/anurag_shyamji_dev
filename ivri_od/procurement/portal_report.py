# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Shared code of the SCMS section reports (RRC DC Summary, RRC Transit Pass,
Gunny Stock Register Details, Lot Search, Rejected Lot, Pending Lot In).

Each report shows one portal section as it is on the portal: one column per
portal column, in the portal's column and row order (rows entered by hand,
see portal_manual.py, are marked "Manual"). The key column (e.g.
DC NO.) opens a row's detail table (lots) in a pop-up; a document column
(e.g. Challan) downloads the PDF saved from the row's Action button."""

import json
import re
from datetime import datetime

import frappe
from frappe import _

from ivri_od.procurement.portal_sync import NOISE_HEADER, normalize_details, parse_key_columns

MAX_RECORDS = 5000


def section_report(
	filters,
	section: str,
	site: str = "SCMS",
	receipt_label=None,
	details: bool = False,
	date_column=None,
	balance=None,
	document_columns=None,
	receipt_columns=None,
	detail_totals=None,
):
	"""Report of one portal section (each SCMS/DCRO report calls this with its section)."""
	filters = frappe._dict(filters or {})
	filters.site = site
	filters.section = section
	if not details:
		filters.show_details = 0
	return execute(
		filters,
		receipt_label=receipt_label,
		date_column=date_column,
		balance=balance,
		document_columns=document_columns,
		receipt_columns=receipt_columns,
		detail_totals=detail_totals,
	)


def execute(
	filters=None,
	receipt_label=None,
	date_column=None,
	balance=None,
	document_columns=None,
	receipt_columns=None,
	detail_totals=None,
):
	"""``receipt_label`` adds a column with the saved document of each row
	(e.g. "Challan" for Transit Challan); the DC report has none.
	``date_column`` (e.g. "Date - A" of the Gunny register) orders the rows by
	that date, so rows entered by hand sit between the portal rows; "Total" last.
	``balance`` adds a worked-out column after the "less" columns, e.g. DCRO
	Paddy Release: Remaining Balance = Paddy Lifted (a running total on the
	portal) - all Paddy Released up to that date. Keys: label, lifted / released
	(words of the column headers; every matching column is added up),
	skip_status (orders whose status contains one of these words release nothing).
	The released total runs over all saved rows of the section in date order,
	per mill (each mill has its own lifting), so it is right even when the report is filtered.
	``document_columns`` (e.g. "Details", "AC Note Doc") add a download column per
	document saved from the row's buttons (Portal Record "documents") and hide the
	portal column of the same name, which holds only the button text.
	``receipt_columns`` (e.g. DCRO View DC: "RRC", "FCI") put the row's saved
	document as a link on the portal column whose cell has the button (View_RRC
	or View_FCI), instead of a separate document column; "No_File" stays text.
	``detail_totals`` add a column per (label, words[, fieldtype]) with the sum of
	the row's detail rows (e.g. DCRO View DC: "Lots"), always shown, also without
	"Show Detail Rows". Fieldtype "Int" shows whole numbers; default Float (3 decimals)."""
	filters = frappe._dict(filters or {})
	records = _get_records(filters)
	if not records:
		return _base_columns(filters, [], [], "", receipt_label), [], None, None, _summary(records, 0)

	cells_by_record = {r.name: _load(r.row_data) for r in records}
	if date_column:
		records.sort(key=lambda r: _date_sort_key(cells_by_record[r.name].get(date_column)))
	data_columns = _ordered_headers(cells_by_record.values())
	if document_columns:
		# The portal's button columns ("Details", "Acnote Doc") hold only the button
		# text; the file columns of the same name below replace them.
		buttons = {_key(label) for label in document_columns}
		data_columns = [h for h in data_columns if _key(h) not in buttons]

	details_by_record = {}
	if filters.show_details or detail_totals:
		details_by_record = _get_details([r.name for r in records])
	detail_columns = []
	if filters.show_details:
		detail_columns = _ordered_headers(d for rows in details_by_record.values() for d in rows)

	# No "detail rows" count column: the portal's own "No. Of Lot" already shows it.
	link_column = _link_column(filters, data_columns)
	columns = _base_columns(filters, data_columns, detail_columns, link_column, receipt_label)
	for idx, label in enumerate(document_columns or []):
		at = len(columns) - 2  # before Last Seen On / Entered From
		columns.insert(at, {"fieldname": f"doc{idx}", "label": _(label), "fieldtype": "Data", "width": 120})
	for idx, (label, _words, *kind) in enumerate(detail_totals or []):
		at = len(columns) - 2  # before Last Seen On / Entered From
		column = {"fieldname": f"t{idx}", "label": _(label), "fieldtype": (kind or ["Float"])[0], "width": 110}
		if column["fieldtype"] == "Float":
			column["precision"] = 3
		columns.insert(at, column)

	balances = {}
	if balance and _quantity_headers(data_columns, balance["released"]):
		balances = _running_balances(filters, balance, date_column)
		after = max(_quantity_headers(data_columns, balance["released"]), key=data_columns.index)
		at = next(i for i, c in enumerate(columns) if c["fieldname"] == f"c{data_columns.index(after)}") + 1
		columns.insert(
			at,
			{"fieldname": "x0", "label": _(balance["label"]), "fieldtype": "Float", "precision": 3, "width": 150},
		)

	data = []
	for record in records:
		row = {
			"record": record.name,  # not a column: the key column opens its details
			"detail_count": record.detail_count,
			"receipt": record.receipt_file,
			"section": record.section,
			"last_seen_on": record.last_seen_on,
			"entry_source": record.entry_source or "Portal",
			"mill_id": record.mill_id or "",
		}
		cells = cells_by_record[record.name]
		for idx, header in enumerate(data_columns):
			row[f"c{idx}"] = cells.get(header, "")
			if record.receipt_file and header in (receipt_columns or ()) and _has_button(row[f"c{idx}"]):
				row[f"c{idx}_file"] = record.receipt_file
		if balances:
			row["x0"] = balances.get(record.name)
		if document_columns:
			saved = _load(record.documents)
			for idx, label in enumerate(document_columns):
				row[f"doc{idx}"] = saved.get(label) or ""

		details = details_by_record.get(record.name) or []
		for idx, (_label, words, *kind) in enumerate(detail_totals or []):
			total = _detail_sum(details, words)
			row[f"t{idx}"] = int(total) if total is not None and kind == ["Int"] else total
		if not filters.show_details:
			details = []
		if not details:
			data.append(row)
			continue
		for detail in details:
			line = dict(row)
			for idx, header in enumerate(detail_columns):
				line[f"d{idx}"] = detail.get(header, "")
			data.append(line)

	return columns, data, None, None, _summary(records, len(data))


def _get_records(filters):
	conditions = [["site", "=", filters.site or "SCMS"]]
	if filters.section:
		conditions.append(["section", "=", filters.section])
	if filters.from_date:
		conditions.append(["last_seen_on", ">=", filters.from_date])
	if filters.to_date:
		conditions.append(["last_seen_on", "<", frappe.utils.add_days(filters.to_date, 1)])
	if filters.entry_source:
		conditions.append(["entry_source", "=", filters.entry_source])
	if filters.mill_id:
		conditions.append(["mill_id", "=", filters.mill_id.strip()])
	if filters.search:
		conditions.append(["row_data", "like", f"%{filters.search.strip()}%"])

	return frappe.get_list(
		"Portal Record",
		filters=conditions,
		fields=[
			"name",
			"section",
			"row_data",
			"detail_count",
			"receipt_file",
			"last_seen_on",
			"seen_run",
			"row_no",
			"entry_source",
			"documents",
			"mill_id",
		],
		order_by="section asc, seen_run desc, row_no asc, last_seen_on desc",
		limit_page_length=MAX_RECORDS,
	)


def _get_details(record_names):
	"""Detail rows of records the user can already read (parents came from get_list)."""
	out = {}
	for d in frappe.get_all(
		"Portal Record Detail",
		filters={"parenttype": "Portal Record", "parent": ["in", record_names]},
		fields=["parent", "detail_data"],
		order_by="parent asc, line_no asc",
	):
		out.setdefault(d.parent, []).append(_load(d.detail_data))
	return out


def _ordered_headers(rows) -> list[str]:
	"""Union of column headers in first-seen order, without serial/link-only columns."""
	headers = []
	seen = set()
	for cells in rows:
		for header in cells:
			if header not in seen and not NOISE_HEADER.match(header):
				seen.add(header)
				headers.append(header)
	return headers


def _link_column(filters, data_columns) -> str:
	"""Fieldname of the column that opens a row's details: the section's first
	key column (DC NO. for DC Monitoring), else the first column."""
	keys = []
	if filters.section:
		site = frappe.get_cached_doc("Portal Site", filters.site or "SCMS")
		section = site.get_section(filters.section)
		keys = [k.lower() for k in parse_key_columns(section.key_columns if section else "")]
	for idx, header in enumerate(data_columns):
		if header.lower() in keys:
			return f"c{idx}"
	return "c0" if data_columns else ""


def _base_columns(filters, data_columns, detail_columns, link_column, receipt_label=None):
	# First column: the mill the row belongs to (each mill reads the portal with its own account).
	columns = [{"fieldname": "mill_id", "label": _("Mill No."), "fieldtype": "Link", "options": "Mill Master", "width": 110}]
	if not filters.section:
		columns.append({"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 170})
	columns += [
		{
			"fieldname": f"c{idx}",
			"label": header,
			"fieldtype": "Data",
			"width": 140,
			"opens_details": f"c{idx}" == link_column,
		}
		for idx, header in enumerate(data_columns)
	]
	columns += [
		{"fieldname": f"d{idx}", "label": _("Detail: {0}").format(header), "fieldtype": "Data", "width": 140}
		for idx, header in enumerate(detail_columns)
	]
	if receipt_label:
		columns.append({"fieldname": "receipt", "label": receipt_label, "fieldtype": "Data", "width": 110})
	columns += [
		{"fieldname": "last_seen_on", "label": _("Last Seen On"), "fieldtype": "Datetime", "width": 160},
		# Manual rows are replaced when the same row is read from the portal.
		{"fieldname": "entry_source", "label": _("Entered From"), "fieldtype": "Data", "width": 110},
	]
	return columns


# Headers that hold a date or a number of a document, not a quantity.
NOT_QUANTITY = re.compile(r"date|\bno\b\.?|number|\bid\b|status", re.IGNORECASE)


def _quantity_headers(headers, words) -> list[str]:
	"""Headers holding a quantity whose text contains all ``words`` (e.g. every "Paddy Lifted" column)."""
	return [h for h in headers if all(w in h.lower() for w in words) and not NOT_QUANTITY.search(h)]


def _sum_of(cells: dict, words):
	values = [_number(cells.get(h)) for h in _quantity_headers(cells, words)]
	values = [v for v in values if v is not None]
	return sum(values) if values else None


def _running_balances(filters, balance, date_column) -> dict:
	"""{record name: lifted - released up to and including that row}, over every
	saved row of the section (not only the filtered ones) of the row's mill, in date then portal order."""
	records = _get_records(frappe._dict(site=filters.site, section=filters.section))
	cells_by_record = {r.name: _load(r.row_data) for r in records}
	if date_column:
		records.sort(key=lambda r: _date_sort_key(cells_by_record[r.name].get(date_column)))
	skip = [w.lower() for w in balance.get("skip_status") or ()]
	released_so_far = {}  # per mill
	out = {}
	for record in records:
		cells = cells_by_record[record.name]
		mill = record.mill_id or ""
		status = " ".join(v for h, v in cells.items() if "status" in h.lower()).lower()
		if not any(w in status for w in skip):
			released_so_far[mill] = released_so_far.get(mill, 0.0) + (_sum_of(cells, balance["released"]) or 0)
		lifted = _sum_of(cells, balance["lifted"])
		out[record.name] = None if lifted is None else round(lifted - released_so_far.get(mill, 0.0), 3)
	return out


def _detail_sum(details, words):
	"""Sum of the quantity columns with ``words`` over a row's detail rows, or None when it has none."""
	values = [_sum_of(d, words) for d in details]
	values = [v for v in values if v is not None]
	return round(sum(values), 3) if values else None


def _number(value):
	try:
		return float(str(value or "").replace(",", "").strip())
	except ValueError:
		return None


def _date_sort_key(value) -> tuple:
	"""dd/mm/yyyy (or dd-mm-yyyy) dates in order, anything else (e.g. "Total") after them."""
	try:
		return (0, datetime.strptime((value or "").strip().replace("-", "/"), "%d/%m/%Y"))
	except ValueError:
		return (1, datetime.max)


def _summary(records, line_count):
	sections = {r.section for r in records}
	return [
		{"label": _("Records"), "value": len(records), "indicator": "Blue", "datatype": "Int"},
		{"label": _("Sections"), "value": len(sections), "indicator": "Blue", "datatype": "Int"},
		{"label": _("Report Lines"), "value": line_count, "indicator": "Green", "datatype": "Int"},
	]


def _has_button(value) -> bool:
	"""True for a portal cell that held a document button (View_RRC), not "No_File" or blank."""
	return bool((value or "").strip()) and not re.search(r"no[\s_-]*file", value, re.IGNORECASE)


def _key(text) -> str:
	"""Letters and digits only, lower case: "AC Note Doc" and "Acnote Doc" are the same column."""
	return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _load(raw) -> dict:
	try:
		value = json.loads(raw or "{}")
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


@frappe.whitelist()
def get_record_details(record: str) -> dict:
	"""Detail table (e.g. the lots of a DC) of one Portal Record, for the pop-up."""
	doc = frappe.get_doc("Portal Record", record)
	doc.check_permission("read")
	footer = _load_list(doc.details_footer)
	return {
		"title": doc.summary or doc.name,
		"rows": [_load(d.detail_data) for d in doc.details],
		"footer": normalize_details(footer) if footer else [],
	}


def _load_list(raw) -> list:
	try:
		value = json.loads(raw or "[]")
	except (TypeError, ValueError):
		return []
	return value if isinstance(value, list) else []
