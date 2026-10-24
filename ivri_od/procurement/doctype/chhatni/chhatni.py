# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ivri_od.procurement.doctype.entry.entry import Entry
from ivri_od.procurement.grn_tp_fulfillment import chhatni_from_rate


class Chhatni(Document):
	def validate(self):
		# Same Transit Pass fetching and validation as Entry: Season + PPC + TP No -> Pass Unique Key.
		Entry._resolve_pass_from_ppc_and_tp_no(self)
		Entry._validate_pass_unique_key(self)
		self._normalize_fields()
		self._validate_one_chhatni_per_pass()
		self._set_net_weight_and_chhatni()
		self._validate_net_weight_above_tp_quantity()

	def _normalize_fields(self):
		if self.pacs_name:
			self.pacs_name = self.pacs_name.strip()

	def _validate_one_chhatni_per_pass(self):
		# Net Weight is the whole pass, so a second record would count the same chhatni twice.
		other = frappe.db.get_value(
			"Chhatni", {"pass_unique_key": self.pass_unique_key, "name": ["!=", self.name or ""]}, "name"
		)
		if other:
			frappe.throw(
				_("Chhatni {0} already exists for TP (Pass Unique Key) {1}. Update that record instead.").format(
					frappe.bold(other), frappe.bold(self.pass_unique_key)
				),
				title=_("Duplicate Chhatni"),
			)

	def _set_net_weight_and_chhatni(self):
		self.net_weight = pass_net_weight(self.pass_unique_key)
		values = chhatni_from_rate(self.net_weight, self.chhatni_kg_per_qtl, self.tp_quantity)
		self.chhatni_kg = values["chhatni_kg"]
		self.chhatni_qt = values["chhatni_qt"]
		self.received_chhatni_pct = values["received_chhatni_pct"]
		if self.net_weight <= 0:
			frappe.msgprint(
				_(
					"No Weigh Bridge net weight found for this TP yet, so Chhatni KG, QT and % are 0. "
					"Save this Chhatni again after weighment."
				),
				title=_("Net Weight Not Found"),
				indicator="orange",
			)


	def _validate_net_weight_above_tp_quantity(self):
		# Chhatni only exists when the pass weighed more than the Transit Pass says: Net Weight > TP Quantity.
		if flt(self.net_weight, 3) <= flt(self.tp_quantity, 3):
			frappe.throw(
				_("Net Weight (QT) {0} must be greater than TP Quantity {1}. Chhatni cannot be saved.").format(
					frappe.bold(flt(self.net_weight, 3)), frappe.bold(flt(self.tp_quantity, 3))
				),
				title=_("Net Weight Not Above TP Quantity"),
			)


def pass_net_weight(pass_unique_key: str | None) -> float:
	"""Net Weight (QT) of a pass: total of its Weigh Bridge Measurements."""
	key = (pass_unique_key or "").strip()
	if not key:
		return 0.0
	total = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(net_weight), 0)
		FROM `tabWeigh Bridge Measurement`
		WHERE pass_unique_key = %s
		""",
		key,
	)[0][0]
	return flt(max(flt(total), 0.0), 3)


@frappe.whitelist()
def get_chhatni_preview(pass_unique_key=None, chhatni_kg_per_qtl=None, tp_quantity=None):
	"""Net Weight and Chhatni values for the form; the saved values are calculated again in validate."""
	frappe.has_permission("Chhatni", "read", throw=True)
	net_weight = pass_net_weight(pass_unique_key)
	return {"net_weight": net_weight, **chhatni_from_rate(net_weight, chhatni_kg_per_qtl, tp_quantity)}
