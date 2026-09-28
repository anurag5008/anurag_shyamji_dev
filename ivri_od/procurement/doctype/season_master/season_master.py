# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


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
