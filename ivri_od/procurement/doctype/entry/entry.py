# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ivri_od.procurement.transit_pass_resolve import get_transit_pass_for_ppc_and_tp_no


class Entry(Document):
	def after_insert(self):
		self._sync_grn_entry_details()
		self._schedule_procurement_rollup_sync()

	def on_update(self):
		self._sync_grn_entry_details()
		previous = self.get_doc_before_save()
		previous_key = (previous.pass_unique_key or "").strip() if previous else ""
		if previous_key and previous_key != (self.pass_unique_key or "").strip():
			self._sync_grn_entry_details(previous_key)
		self._schedule_procurement_rollup_sync(previous_key)

	def _schedule_procurement_rollup_sync(self, previous_key: str | None = None):
		keys = {(self.pass_unique_key or "").strip()}
		if previous_key:
			keys.add((previous_key or "").strip())
		keys.discard("")
		for key in keys:
			frappe.db.after_commit(lambda k=key: _sync_procurement_rollups_for_pass(k))

	def validate(self):
		self._resolve_pass_from_ppc_and_tp_no()
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

	def _resolve_pass_from_ppc_and_tp_no(self):
		tp_no = (self.tp_no or "").strip()
		ppc_name = (self.ppc_name or "").strip()
		season = (self.season or "").strip()
		if not season:
			frappe.throw(_("Season is required to fetch the Pass Unique Key."))
		if not ppc_name or not tp_no:
			frappe.throw(_("PPC and TP No are required to fetch the Pass Unique Key."))
		tp_row = get_transit_pass_for_ppc_and_tp_no(ppc_name, tp_no, season=season)
		if not tp_row:
			frappe.throw(
				_(
					"No PPAS Transit Pass found for Season {0}, TP No {1}, and PPC {2}. "
					"Check season, TP No, and PPC on the transit pass import."
				).format(frappe.bold(season), frappe.bold(tp_no), frappe.bold(ppc_name))
			)
		key = (tp_row.get("pass_unique_key") or tp_row.get("name") or "").strip()
		if not key:
			frappe.throw(_("Transit pass found but Pass Unique Key is missing."))
		self.pass_unique_key = key
		self.tp_no = tp_no
		self.transit_pass_no = (tp_row.get("transit_pass_no") or tp_no).strip()
		self.tp_quantity = flt(tp_row.get("quantity"))
		self.pacs_name = (tp_row.get("pacs") or "").strip()

	def _validate_pass_unique_key(self):
		key = (self.pass_unique_key or "").strip()
		self.pass_unique_key = key
		if not key:
			frappe.throw(_("Pass Unique Key could not be resolved. Enter PPC and TP No."))

		if not frappe.db.exists("PPAS Transit Pass", {"pass_unique_key": key}):
			frappe.throw(
				_("No PPAS Transit Pass found for Pass Unique Key {0}.").format(frappe.bold(key))
			)

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


def resolve_pass_unique_key_from_ppc_tp(
	ppc_name: str, tp_no: str, season: str | None = None
) -> str | None:
	row = get_transit_pass_for_ppc_and_tp_no(ppc_name, tp_no, season=season)
	if not row:
		return None
	return (row.get("pass_unique_key") or row.get("name") or "").strip() or None


def _sync_procurement_rollups_for_pass(pass_unique_key: str) -> None:
	from ivri_od.procurement.procurement_sync import sync_procurement_from_pass

	sync_procurement_from_pass((pass_unique_key or "").strip())


@frappe.whitelist()
def resolve_entry_pass_from_ppc_tp(ppc_name=None, tp_no=None, season=None):
	row = get_transit_pass_for_ppc_and_tp_no(ppc_name, tp_no, season=season)
	if not row:
		return {}
	key = (row.get("pass_unique_key") or row.get("name") or "").strip()
	return {
		"pass_unique_key": key,
		"transit_pass_no": row.get("transit_pass_no"),
		"quantity": row.get("quantity"),
		"pacs": row.get("pacs"),
	}
