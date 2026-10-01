# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import base64
import json
import re
from datetime import date, datetime, time as dt_time
from io import BytesIO

import frappe
from frappe import _
from frappe.model.document import Document
import openpyxl


class PPASDataExtraction(Document):
	def before_insert(self):
		if not self.status:
			self.status = "Draft"

	def validate(self):
		if not self.season:
			frappe.throw(frappe._("Season is required"))

	@frappe.whitelist()
	def load_ppas_sessions(self):
		"""Load available PPAS sessions for the selected season."""
		self.status = "Sessions Loaded"
		self.save(ignore_permissions=True)
		frappe.msgprint(frappe._("PPAS sessions loaded for season {0}").format(self.season))
		return {"status": self.status}

	@frappe.whitelist()
	def extract_data(self):
		"""Extract PPAS data for the selected season."""
		self.status = "Extracted"
		if not self.records_extracted:
			self.records_extracted = 0
		self.save(ignore_permissions=True)
		frappe.msgprint(frappe._("Data extraction completed for season {0}").format(self.season))
		return {
			"status": self.status,
			"records_extracted": self.records_extracted,
		}

	@frappe.whitelist()
	def download_excel_file(self):
		"""Return the Excel download URL for the extracted file."""
		if not self.download_url and not self.excel_file:
			frappe.throw(frappe._("No Excel file available. Extract data first."))

		self.status = "Ready for Download"
		self.save(ignore_permissions=True)
		return {
			"excel_file": self.excel_file,
			"download_url": self.download_url,
		}

	@frappe.whitelist()
	def close_ppas_session(self):
		"""Close the active PPAS session."""
		self.status = "Session Closed"
		self.save(ignore_permissions=True)
		frappe.msgprint(frappe._("PPAS session closed"))
		return {"status": self.status}


def _normalize_ppas_season_key(season):
	return re.sub(r"\s+", "", (season or "").strip().lower())


def _parse_ppas_season_options(ppas_seasons):
	if isinstance(ppas_seasons, str):
		ppas_seasons = json.loads(ppas_seasons)

	if isinstance(ppas_seasons, list):
		return [str(item).strip() for item in ppas_seasons if str(item).strip()]

	if isinstance(ppas_seasons, dict):
		return [str(key).strip() for key in ppas_seasons.keys() if str(key).strip()]

	return []


@frappe.whitelist()
def get_ppas_season_for_extract(season_master_name, ppas_seasons=None):
	"""Map a Season Master label (e.g. Kharif 2026) to a PPAS portal season (Kharif(2026))."""
	season_master_name = (season_master_name or "").strip()
	if not season_master_name:
		frappe.throw(_("Season Master name is required"))

	options = _parse_ppas_season_options(ppas_seasons)
	if not options:
		frappe.throw(
			_("No PPAS seasons available. Click Load PPAS Sessions on PPAS Data Extraction first.")
		)

	master_key = _normalize_ppas_season_key(season_master_name)
	for option in options:
		if _normalize_ppas_season_key(option) == master_key:
			return {"season": option}

	master_match = re.match(
		r"^(Kharif|Rabi)\s+(\d{4})$",
		season_master_name,
		flags=re.IGNORECASE,
	)
	if master_match:
		candidate = f"{master_match.group(1).capitalize()}({master_match.group(2)})"
		for option in options:
			if _normalize_ppas_season_key(option) == _normalize_ppas_season_key(candidate):
				return {"season": option}

	frappe.throw(
		_(
			"Could not match Season Master {0} to any PPAS portal season. "
			"Load PPAS Sessions first, then pick a matching season."
		).format(season_master_name)
	)


def _serialize_excel_cell(value):
	if isinstance(value, datetime):
		return value.strftime("%d-%b-%Y %H:%M:%S")
	if isinstance(value, date):
		return value.isoformat()
	if isinstance(value, dt_time):
		return value.strftime("%H:%M:%S")
	return value


@frappe.whitelist()
def parse_ppas_excel_file(file_content):
	"""Parse PPAS Agent Excel export into row dicts (header row = keys)."""
	if not file_content:
		frappe.throw(_("Excel file content is required"))

	try:
		raw = base64.b64decode(file_content)
	except Exception:
		frappe.throw(_("Invalid Excel file content"))

	try:
		workbook = openpyxl.load_workbook(BytesIO(raw), read_only=True, data_only=True)
	except Exception as exc:
		frappe.throw(_("Unable to read PPAS Excel file: {0}").format(exc))

	worksheet = workbook.active
	row_iter = worksheet.iter_rows(values_only=True)

	try:
		header_row = next(row_iter)
	except StopIteration:
		return []

	headers = []
	for index, cell in enumerate(header_row):
		label = "" if cell is None else str(cell).strip()
		if not label:
			label = f"column_{index + 1}"
		headers.append(label)

	records = []
	for row in row_iter:
		if not row or all(cell is None or str(cell).strip() == "" for cell in row):
			continue

		item = {}
		for index, key in enumerate(headers):
			cell = row[index] if index < len(row) else None
			item[key] = _serialize_excel_cell(cell)
		records.append(item)

	from ivri_od.procurement.doctype.ppas_transit_pass.ppas_import import standardize_ppas_rows

	return standardize_ppas_rows(records)
