# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

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


def season_year_for(crop_season, start_date) -> str:
	"""Season year of a start date. Kharif comes first in a season year, so Rabi belongs to the year before."""
	year = getdate(start_date).year
	return str(year - 1 if crop_season == "Rabi" else year)


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


def get_season_code(season_master: str | None) -> str:
	"""Season Code of a Season Master; falls back to the code derived from its name (Kharif 2025 -> K25)."""
	if not season_master:
		return ""
	if frappe.db.has_column("Season Master", "season_code"):
		code = (frappe.db.get_value("Season Master", season_master, "season_code") or "").strip()
		if code:
			return code.upper()
	return short_season_code(season_master)


def get_season_for_date(date) -> str | None:
	"""Season Master whose Start Date - End Date range covers the date."""
	if not date or not frappe.db.has_column("Season Master", "start_date"):
		return None
	date = getdate(date)
	rows = frappe.get_all(
		"Season Master",
		filters={"start_date": ["<=", date], "end_date": [">=", date]},
		pluck="name",
		order_by="start_date desc",
		limit=1,
	)
	return rows[0] if rows else None


class SeasonMaster(Document):
	def before_insert(self):
		# The name is "{crop_season} {year}" and is set right after this hook, before before_validate.
		self._sync_year_name_and_code()

	def before_validate(self):
		self._sync_year_name_and_code()

	def _sync_year_name_and_code(self):
		"""Year from Start Date; Season Name and Season Code from Season Type + Year.

		Kharif takes the year of its Start Date (Kharif Nov 2025 -> K25). Rabi follows Kharif but belongs
		to the previous year (Rabi May 2026 -> R25).
		Seasons created in code without a Start Date keep the Year they were given.
		A saved season keeps its Year while its Season Type and Start Date are unchanged.
		"""
		if self.meta.has_field("start_date") and self.start_date and not self._dates_unchanged():
			self.year = season_year_for(self.crop_season, self.start_date)
		if self.year:
			self.year = str(self.year).strip()
		self.season_name = (
			f"{self.crop_season} {self.year}" if self.crop_season and self.year else ""
		)
		if self.meta.has_field("season_code"):
			self.season_code = short_season_code(self.season_name) if self.season_name else ""

	def _dates_unchanged(self) -> bool:
		before = None if self.is_new() else self.get_doc_before_save()
		return bool(
			before
			and before.year
			and before.crop_season == self.crop_season
			and before.start_date
			and getdate(before.start_date) == getdate(self.start_date)
		)

	def validate(self):
		if not self.is_new():
			self._validate_name_parts_unchanged()
		if self.meta.has_field("season_code"):
			self._validate_unique_season_code()
		if self.meta.has_field("start_date"):
			self._validate_date_range()

	def _validate_name_parts_unchanged(self):
		"""Saved seasons are named "{Season Type} {Year}" and linked by that name, so both must stay."""
		before = self.get_doc_before_save()
		if not before:
			return
		old_label = f"{before.crop_season or ''} {str(before.year or '').strip()}".strip()
		if self.season_name and old_label and self.season_name != old_label:
			frappe.throw(
				_(
					"This season is {0}. The Season Type or Start Date you entered makes it {1}. "
					"Create a new Season Master for {1} instead."
				).format(frappe.bold(old_label), frappe.bold(self.season_name)),
				title=_("Season Type / Year Cannot Change"),
			)

	def _validate_unique_season_code(self):
		if not self.season_code:
			return
		other = frappe.db.get_value(
			"Season Master", {"season_code": self.season_code, "name": ["!=", self.name or ""]}, "name"
		)
		if other:
			frappe.throw(
				_("Season Code {0} is already used by {1}.").format(frappe.bold(self.season_code), other),
				title=_("Duplicate Season Code"),
			)

	def _validate_date_range(self):
		if not self.start_date and not self.end_date:
			return
		if not (self.start_date and self.end_date):
			frappe.throw(_("Enter both Start Date and End Date."), title=_("Season Dates"))
		if getdate(self.end_date) < getdate(self.start_date):
			frappe.throw(_("End Date cannot be before Start Date."), title=_("Season Dates"))

		# One RST date must map to one season.
		overlap = frappe.db.get_value(
			"Season Master",
			{
				"name": ["!=", self.name or ""],
				"start_date": ["<=", self.end_date],
				"end_date": [">=", self.start_date],
			},
			"name",
		)
		if overlap:
			frappe.throw(
				_("Season dates overlap with {0}. Each date can belong to only one season.").format(overlap),
				title=_("Season Dates"),
			)
