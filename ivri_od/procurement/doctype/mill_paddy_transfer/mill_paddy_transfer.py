# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class MillPaddyTransfer(Document):
	"""Paddy received by a mill from another mill, entered by hand. Only submitted entries are
	counted as "Transfer from other Mill" in the Joint Custody and Maintenance Charge Report."""

	def validate(self):
		if self.mill == self.from_mill:
			frappe.throw(_("From Mill No and Receiving Mill No must be different"))
		if flt(self.quantity) <= 0:
			frappe.throw(_("Quantity (Qtl) must be more than 0"))
		self.quantity = flt(self.quantity, 2)
