# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from ivri_od.procurement import portal_sync

# Run-row field -> key in the portal_sync.import_rows result.
RUN_COUNTS = {
	"records_inserted": "inserted",
	"records_updated": "updated",
	"records_unchanged": "unchanged",
	"records_failed": "failed",
	"receipts_saved": "receipts",
}


# "Rows to Save" option -> rows kept per Search (same list in portal_data_extraction.js).
ROW_LIMITS = {"Latest Entry": 1, "Last 5": 5, "Last 10": 10, "Last 20": 20}


class PortalDataExtraction(Document):
	def validate(self):
		if not frappe.get_cached_value("Portal Site", self.site, "enabled"):
			frappe.throw(_("Portal site {0} is disabled").format(self.site))
		if self.mill and not frappe.db.get_value("Mill Master", self.mill, "is_active"):
			frappe.throw(_("Mill No. {0} is not active in Mill Master").format(self.mill))
		self._update_totals()

	def _update_totals(self):
		"""Header totals are the sum of all runs."""
		self.records_extracted = sum(cint(r.records_extracted) for r in self.runs)
		for field in RUN_COUNTS:
			self.set(field, sum(cint(r.get(field)) for r in self.runs))

	def get_run(self, run: str):
		for row in self.runs:
			if row.name == run:
				return row
		frappe.throw(_("Extraction run {0} not found").format(run))


def _get_writable(name: str) -> PortalDataExtraction:
	doc = frappe.get_doc("Portal Data Extraction", name)
	doc.check_permission("write")
	return doc


@frappe.whitelist()
def get_session_config(name: str) -> dict:
	"""What the local agent needs to open Chrome for this extraction."""
	doc = frappe.get_doc("Portal Data Extraction", name)
	doc.check_permission("read")
	_require_mill(doc)
	site = frappe.get_cached_doc("Portal Site", doc.site)
	return {
		"site": doc.site,
		"login_url": site.login_url,
		"download_receipts": cint(doc.download_receipts),
		# "Rows to Save": the agent stops paging once it has read this many newest rows (0 = all).
		"row_limit": ROW_LIMITS.get(doc.rows_to_save, 0),
		# Pages whose rows have a detail link (e.g. DC Monitoring → View) to open per row.
		# A table id with no link text is read on the row's document page before it is
		# printed (e.g. DCRO View DC: the lots in grdDepotFCIbody).
		"detail_links": [
			{"page_match": row.page_match, "link_text": row.detail_link_text or "", "table_id": row.detail_table_id or ""}
			for row in site.sections
			if row.enabled and row.page_match and (row.detail_link_text or row.detail_table_id)
		],
		# Pages with several tables or tabs: which table to read (see Portal Site Section "Table Match").
		"grid_matches": [
			{"page_match": row.page_match, "table_match": row.table_match}
			for row in site.sections
			if row.enabled and row.page_match and row.table_match
		],
		# Buttons or elements besides Search/Show that start a read (e.g. DCRO Paddy Release: Save, dvmillerhistory).
		"click_triggers": [
			# only: read after these clicks only, not after any Search/Show-like click.
			{"page_match": row.page_match, "triggers": row.extract_on_click, "only": cint(row.extract_only_on_click)}
			for row in site.sections
			if row.enabled and row.page_match and row.extract_on_click
		],
		# Pages read as soon as they open, without a Search click (e.g. WINGS e_tec).
		"open_reads": [row.page_match for row in site.sections if row.enabled and row.page_match and row.read_on_open],
		# Words before the mill's ID on the dashboard or page (e.g. Mill ID, Miller Code).
		"mill_id_labels": site.get("mill_id_labels") or portal_sync.DEFAULT_MILL_LABELS,
		# Rows already in the ERP: the agent reads only new or changed rows ("Read Only New Rows").
		"known_rows": [] if cint(doc.read_full_table) else _known_rows(site),
		# Element showing the mill's ID (e.g. WINGS dashboard header); tried first.
		"mill_id_xpath": site.get("mill_id_xpath") or "",
		# Pages (or tabs, by Table Match) whose row document (e.g. Transit Challan, Lot Search Print) is always saved as PDF.
		"receipt_links": [
			{"page_match": row.page_match, "link_text": row.receipt_link_text or "", "table_match": row.table_match or ""}
			for row in site.sections
			if row.enabled and row.page_match and row.download_receipt
		],
	}


MAX_KNOWN_ROWS = 20000


def _require_mill(doc):
	"""Each mill has its own portal account: the Mill No. is picked before Chrome opens."""
	if not doc.mill:
		frappe.throw(_("Select the Mill No. whose portal account you will log in with, then save."))


def _check_portal_mill(doc, found: str):
	"""Stop when the portal shows another mill of Mill Master than the one picked
	(logged in with the wrong account), so no row is saved under the wrong mill.
	A code that is not in Mill Master (e.g. the WINGS portal's own mill code) is only noted."""
	found = (found or "").strip()
	if found and found.upper() != doc.mill.upper() and frappe.db.exists("Mill Master", found):
		frappe.throw(
			_("The portal is logged in as mill {0}, but Mill No. {1} is picked on this form. Nothing was saved. Log in with the account of {1}, or make a new extraction for {0}.").format(
				found, doc.mill
			)
		)


def _known_rows(site) -> list[dict]:
	"""Per section with "Read Only New Rows": fingerprints of the rows read from the portal."""
	out = []
	for row in site.sections:
		if not (row.enabled and row.page_match and row.read_new_only):
			continue
		sigs = frappe.get_all(
			"Portal Record",
			filters={
				"site": site.name,
				"section": row.section_name,
				"entry_source": "Portal",
				"portal_row_sig": ["is", "set"],
			},
			pluck="portal_row_sig",
			order_by="last_seen_on desc",
			limit=MAX_KNOWN_ROWS,
		)
		out.append({"page_match": row.page_match, "table_match": row.table_match or "", "sigs": sigs})
	return out


@frappe.whitelist(methods=["POST"])
def mark_connected(name: str):
	doc = _get_writable(name)
	doc.status = "Connected"
	portal_sync.append_log(doc, _("Chrome opened. Waiting for login and Search."))
	doc.save()
	return doc.status


@frappe.whitelist(methods=["POST"])
def begin_run(
	name: str,
	total_rows: int,
	pages: int = 1,
	columns=None,
	page_url: str | None = None,
	page_heading: str | None = None,
	page_title: str | None = None,
	table_id: str | None = None,
	table_title: str | None = None,
	active_tab: str | None = None,
	table_ids: str | None = None,
	page_filters=None,
	mill_id: str | None = None,
	rows_kept: int | None = None,
	kept_note: str | None = None,
) -> dict:
	"""Start a run for one Search: name its section from the page (and, on pages
	with several tables or tabs, from the table read) and add a run row.
	``page_filters`` are the search filters on the page ([{label, id, value}]);
	the ones named in the section's "Page Filter Columns" are saved with every row."""
	doc = _get_writable(name)
	_require_mill(doc)
	_check_portal_mill(doc, mill_id)
	site = frappe.get_cached_doc("Portal Site", doc.site)
	table_info = {"table_id": table_id, "table_title": table_title, "active_tab": active_tab, "table_ids": table_ids}
	section = site.resolve_section(page_url, page_heading, page_title, table_info)
	page_filters = portal_sync.safe_page_filters(
		frappe.parse_json(page_filters) if isinstance(page_filters, str) else page_filters
	)
	section_row = site.get_section(section)
	filter_values = portal_sync.filter_cells(section_row.filter_columns if section_row else "", page_filters)

	run = doc.append(
		"runs",
		{
			"section": section,
			"status": "Running",
			"extracted_on": now_datetime(),
			"records_extracted": cint(total_rows),
			"page_heading": (page_heading or "")[:140],
			"page_url": page_url or "",
			"page_filters": json.dumps(filter_values, ensure_ascii=False) if filter_values else "",
			# The Mill No. picked on the form: the mill of every row of this run.
			"mill_id": doc.mill,
		},
	)
	if (mill_id or "").strip():
		doc.mill_id = (mill_id or "").strip()[:60]  # the mill's ID as shown on the portal, for checking
	column_list = frappe.parse_json(columns) if isinstance(columns, str) else (columns or [])
	portal_sync.append_log(
		doc,
		_("Search on '{0}': {1} rows on {2} page(s), Mill No. {3} (portal shows {4}). Columns: {5}").format(
			section,
			cint(total_rows),
			cint(pages),
			run.mill_id,
			(mill_id or "").strip() or _("no mill ID"),
			", ".join(str(c) for c in column_list[:30]),
		),
	)
	if rows_kept is not None and cint(rows_kept) < cint(total_rows):
		# "Rows to Save" on the form (e.g. Last 5 while testing a page).
		portal_sync.append_log(
			doc,
			_("Rows to Save is {0}: saving {1} of {2} rows ({3}).").format(
				doc.rows_to_save, cint(rows_kept), cint(total_rows), kept_note or ""
			),
		)
	if table_id or table_title or active_tab:
		# Shown so "Table Match" can be filled in for pages with several tables or tabs.
		portal_sync.append_log(
			doc,
			_("Table read: id '{0}', title '{1}', open tab '{2}'").format(
				table_id or "", (table_title or "")[:100], (active_tab or "")[:100]
			),
		)
	if section_row and section_row.filter_columns:
		# Shown so "Page Filter Columns" can be checked against the labels on the page.
		portal_sync.append_log(
			doc,
			_("Page filters: {0}. Saved with each row: {1}").format(
				"; ".join(
					f"{f.get('label') or f.get('id') or '?'} = {f.get('value')}"
					for f in page_filters[:20]
				)
				or _("none found"),
				", ".join(f"{k} = {v}" for k, v in filter_values.items()) or _("nothing"),
			),
		)
	doc.save()
	return {"run": run.name, "section": section}


@frappe.whitelist(methods=["POST"])
def import_rows(name: str, run: str, rows):
	"""Save one batch of scraped rows under the run's section."""
	doc = _get_writable(name)
	run_row = doc.get_run(run)
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	if not isinstance(rows, list):
		frappe.throw(_("Rows must be a list"))

	extra_cells = frappe.parse_json(run_row.page_filters) if run_row.page_filters else {}
	result = portal_sync.import_rows(
		doc.site,
		run_row.section,
		doc.name,
		rows,
		seen_run=run_row.extracted_on,
		extra_cells=extra_cells,
		mill_id=run_row.mill_id or "",
	)

	doc.reload()
	run_row = doc.get_run(run)
	for field, key in RUN_COUNTS.items():
		run_row.set(field, cint(run_row.get(field)) + result[key])
	for error in result["errors"]:
		portal_sync.append_log(doc, error)
	doc.save()
	return result


@frappe.whitelist(methods=["POST"])
def finish_run(name: str, run: str, status: str, message: str | None = None):
	doc = _get_writable(name)
	if status not in ("Completed", "Failed"):
		frappe.throw(_("Invalid status {0}").format(status))
	run_row = doc.get_run(run)
	run_row.status = status
	doc.status = status
	doc.last_extracted_on = now_datetime()
	doc.last_section = run_row.section  # list column: which page was read last
	portal_sync.append_log(
		doc,
		message
		or _("'{0}' {1}: {2} new, {3} updated, {4} unchanged, {5} errors, {6} receipts.").format(
			run_row.section,
			status,
			run_row.records_inserted,
			run_row.records_updated,
			run_row.records_unchanged,
			run_row.records_failed,
			run_row.receipts_saved,
		),
	)
	doc.save()
	return {"section": run_row.section, "status": status}
