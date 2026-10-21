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

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.model.document import Document
from frappe.utils import cint, now_datetime
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
	"""Section's "Page Filter Columns": lines "Column Name = words in the filter's label or id"."""
	out = []
	for line in (filter_columns or "").splitlines():
		name, _sep, match = line.partition("=")
		name = _squash(name)
		if name:
			out.append((name, _squash(match) or name))
	return out


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
		wanted = _match_key(match)
		for item in page_filters:
			if not isinstance(item, dict):
				continue
			value = _squash(item.get("value"))
			where = _match_key(f"{item.get('label') or ''} {item.get('id') or ''}")
			if wanted and wanted in where and value and not PLACEHOLDER_VALUE.match(value):
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

	result = {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 0, "receipts": 0, "errors": []}
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


def _upsert_row(extraction, row: dict, key_columns: list[str]) -> tuple[str, Document]:
	cells = normalize_cells(row.get("cells"))
	if extraction.extra_cells:
		cells = {**normalize_cells(extraction.extra_cells), **cells}
	cells = fix_section_cells(extraction.section, cells)
	record_key = build_record_key(cells, key_columns)
	mill_id = row_mill_id(cells, extraction.mill_label_keys or mill_label_keys(None), extraction.mill_id)
	name = resolve_record_name(extraction.site, extraction.section, record_key, mill_id)
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
		record_key = build_record_key(cells, key_columns)
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
