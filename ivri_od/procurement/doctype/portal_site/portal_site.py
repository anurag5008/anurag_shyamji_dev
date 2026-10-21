# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import re
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document

SECTION_NAME_LENGTH = 140
GENERIC_PAGE_NAMES = {"", "default", "index", "home", "main", "dashboard", "welcome"}


class PortalSite(Document):
	def validate(self):
		seen = set()
		for row in self.sections:
			row.section_name = (row.section_name or "").strip()
			row.page_match = (row.page_match or "").strip()
			key = row.section_name.lower()
			if key in seen:
				frappe.throw(_("Row {0}: section {1} is listed twice").format(row.idx, row.section_name))
			seen.add(key)

	def get_section(self, section_name: str):
		"""Return the enabled section row by name, or None."""
		wanted = (section_name or "").strip().lower()
		for row in self.sections:
			if row.enabled and row.section_name.lower() == wanted:
				return row
		return None

	def resolve_section(
		self, page_url: str, page_heading: str = "", page_title: str = "", table_info: dict | None = None
	) -> str:
		"""Name the section a scraped table belongs to.

		1. A configured section whose "Page URL Contains" text is in the page URL.
		   When several sections share a page (tabs, several tables), the one whose
		   "Table Match" is in the table's id, its title, the open tab's label or the
		   id of an element around the table wins;
		   a section without Table Match is the page's default, and a page with
		   only one section always uses it.
		2. The open tab's label, then the page file name, e.g.
		   CMR_TransitChallanView_WB.aspx -> "CMR Transit Challan View WB".
		3. The page heading, then the browser title.
		"""
		url = (page_url or "").lower()
		table_info = table_info or {}
		on_page = [r for r in self.sections if r.enabled and r.page_match and r.page_match.lower() in url]
		# Strongest evidence first: the open tab, then the table id, then the text above
		# the table (which may be a whole tab bar naming every tab).
		for source in ("active_tab", "table_id", "table_title"):
			text = _match_key(table_info.get(source))
			for row in on_page:
				if text and row.table_match and _match_key(row.table_match) in text:
					return row.section_name
		# Last: the ids around the table, one by one (WINGS: the table inside div#report_div).
		ids = [_match_key(i) for i in (table_info.get("table_ids") or "").split()]
		for row in on_page:
			if row.table_match and any(_match_key(row.table_match) in i for i in ids):
				return row.section_name
		for row in on_page:
			if not row.table_match:
				return row.section_name
		if len(on_page) == 1:
			return on_page[0].section_name  # the page's only section, even if its table title was not found

		for candidate in (table_info.get("active_tab"), _name_from_url(page_url), page_heading, page_title):
			candidate = re.sub(r"\s+", " ", candidate or "").strip()
			if candidate:
				return candidate[:SECTION_NAME_LENGTH]
		return _("Unknown Page")


def _match_key(text: str) -> str:
	"""Lower case letters and digits only: "Rejected Lot" matches id "gvRejectedLot"."""
	return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _name_from_url(page_url: str) -> str:
	stem = urlparse(page_url or "").path.rstrip("/").rsplit("/", 1)[-1]
	stem = re.sub(r"\.\w+$", "", stem)
	if stem.lower() in GENERIC_PAGE_NAMES:
		return ""
	return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|[_\-]+", " ", stem).strip()
