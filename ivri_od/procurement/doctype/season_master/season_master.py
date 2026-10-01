# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import re

import frappe
from frappe.model.document import Document

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import short_season_code


def resolve_season_master_name(season_text: str | None) -> str | None:
	"""Season Master name from TP season text (e.g. Kharif 2025, K25)."""
	text = (season_text or "").strip()
	if not text:
		return None
	if frappe.db.exists("Season Master", text):
		return text

	short = re.match(r"^([KR])(\d{2})$", text, re.IGNORECASE)
	if short:
		crop = "Kharif" if short.group(1).upper() == "K" else "Rabi"
		year = f"20{short.group(2)}"
		candidate = f"{crop} {year}"
		if frappe.db.exists("Season Master", candidate):
			return candidate

	normalized = text.replace("(", " ").replace(")", " ").replace("_", " ")
	normalized = " ".join(normalized.split())

	for row in frappe.get_all("Season Master", fields=["name", "crop_season", "year"], limit_page_length=0):
		label = f"{row.crop_season} {row.year}".strip()
		if text.casefold() == label.casefold():
			return row.name
		if normalized.casefold() == label.casefold():
			return row.name
		if text.casefold() == short_season_code(label).casefold():
			return row.name
	return None


def get_or_create_season_master(crop_season, year):
	crop = (crop_season or "").strip()
	year_text = str(year or "").strip()
	if not crop or not year_text:
		return None

	name = f"{crop} {year_text}"
	if frappe.db.exists("Season Master", name):
		return name

	frappe.get_doc(
		{
			"doctype": "Season Master",
			"crop_season": crop,
			"year": year_text,
		}
	).insert(ignore_permissions=True)
	return name


class SeasonMaster(Document):
	def before_validate(self):
		if self.year:
			self.year = str(self.year).strip()
		self.season_name = (
			f"{self.crop_season} {self.year}" if self.crop_season and self.year else ""
		)
