# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, format_datetime, get_datetime

from ivri_od.procurement.pass_print import (
	qr_content_entry,
	qr_image_html,
	render_template_file,
	send_pdf_download,
)


class Entry(Document):
	def after_insert(self):
		self._sync_grn_entry_details()

	def on_update(self):
		self._sync_grn_entry_details()
		previous = self.get_doc_before_save()
		previous_key = (previous.pass_unique_key or "").strip() if previous else ""
		if previous_key and previous_key != (self.pass_unique_key or "").strip():
			self._sync_grn_entry_details(previous_key)

	def validate(self):
		self._validate_pass_unique_key()
		self._normalize_fields()
		self._validate_available_quantity()
		self._update_total_amount()

	def _sync_grn_entry_details(self, pass_unique_key=None):
		key = (pass_unique_key or self.pass_unique_key or "").strip()
		if not key:
			return
		from ivri_od.procurement.doctype.grn_note.grn_note import (
			sync_grn_entry_details_for_pass,
		)

		sync_grn_entry_details_for_pass(key)

	def _validate_pass_unique_key(self):
		key = (self.pass_unique_key or "").strip()
		self.pass_unique_key = key
		if not key:
			frappe.throw(_("Select TP (Pass Unique Key) from PPAS Transit Pass."))

		if not frappe.db.exists("PPAS Transit Pass", {"pass_unique_key": key}):
			frappe.throw(
				_("No PPAS Transit Pass found for Pass Unique Key {0}.").format(frappe.bold(key))
			)

		tp = frappe.db.get_value(
			"PPAS Transit Pass",
			{"pass_unique_key": key},
			["transit_pass_no", "quantity", "pacs"],
			as_dict=True,
		)
		if not tp:
			return

		self.transit_pass_no = tp.transit_pass_no
		self.tp_quantity = flt(tp.quantity)
		self.pacs_name = (tp.pacs or "").strip()

	def _validate_available_quantity(self):
		key = (self.pass_unique_key or "").strip()
		if not key:
			return

		tp_quantity = flt(self.tp_quantity)
		entry_total = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(entry_quantity), 0)
			FROM `tabEntry`
			WHERE pass_unique_key = %s AND name != %s
			""",
			(key, self.name or ""),
			as_list=True,
		)[0][0]
		grn_net_total = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(net_weight), 0)
			FROM `tabGRN Note`
			WHERE pass_unique_key = %s AND docstatus < 2
			""",
			(key,),
			as_list=True,
		)[0][0]

		available = max(tp_quantity - flt(entry_total) - flt(grn_net_total), 0)
		if flt(self.entry_quantity, 3) > flt(available, 3):
			frappe.throw(
				_(
					"Entry Quantity {0} QT exceeds the {1} QT still available for this TP. "
					"TP quantity: {2} QT; existing Entry quantity: {3} QT; GRN net weight: {4} QT."
				).format(
					frappe.bold(flt(self.entry_quantity, 3)),
					frappe.bold(flt(available, 3)),
					flt(tp_quantity, 3),
					flt(entry_total, 3),
					flt(grn_net_total, 3),
				),
				title=_("TP Quantity Exceeded"),
			)

	def _normalize_fields(self):
		if self.agent_name:
			self.agent_name = self.agent_name.strip()
		if self.pacs_name:
			self.pacs_name = self.pacs_name.strip()

	def _update_total_amount(self):
		self.total_amount = flt(self.entry_quantity) * flt(self.entry_price_per_quintal)


def _entry_datetime_display(doc) -> str:
	if doc.entry_date and doc.entry_time:
		return format_datetime(get_datetime(f"{doc.entry_date} {doc.entry_time}"))
	if doc.entry_date:
		return format_datetime(get_datetime(str(doc.entry_date)))
	return "—"


def _render_entry_pass_html(doc, for_pdf: bool = False) -> str:
	entry_datetime_display = _entry_datetime_display(doc)
	qr_text = qr_content_entry(doc, entry_datetime_display)
	return render_template_file(
		("procurement", "doctype", "entry", "entry_pass.html"),
		{
			"doc": doc,
			"entry_datetime_display": entry_datetime_display,
			"qr_image": qr_image_html(qr_text),
			"qr_text": qr_text,
			"for_pdf": for_pdf,
		},
	)


@frappe.whitelist()
def get_entry_pass_html(name: str) -> str:
	doc = frappe.get_doc("Entry", name)
	doc.check_permission("print")
	return _render_entry_pass_html(doc)


@frappe.whitelist()
def download_entry_pass_pdf(name: str):
	doc = frappe.get_doc("Entry", name)
	doc.check_permission("print")
	html = _render_entry_pass_html(doc, for_pdf=True)
	send_pdf_download(html, f"{doc.name}-entry-pass.pdf")
