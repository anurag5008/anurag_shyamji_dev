# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Excess Received Qty typed in the Mandi Book for one Transit Pass (Pass Unique Key).

It is the quantity received above the TP Quantity that is paddy, not Chhatni. The Mandi Book takes it
away from (Total Qty Received - TP Qty) to get the Chhatni (QT)."""

from frappe.model.document import Document
from frappe.utils import flt


class ChhatniExcess(Document):
	def validate(self):
		self.pass_unique_key = (self.pass_unique_key or "").strip()
		self.excess_qty = flt(self.excess_qty, 3)
