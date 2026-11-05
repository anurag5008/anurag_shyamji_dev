# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""One RST (GRN Note) that holds the goods of several Transit Passes.

The weighbridge cannot know this at weighing time, so staff split the RST later in the Mandi Book:
each TP No gets its own Qty. The Mandi Book then counts the RST under each TP for that Qty (gross,
gunny, deduction and bags in the same proportion). The GRN Note itself is not changed.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

TOLERANCE = 0.001


class MandiBookTPSplit(Document):
	def validate(self):
		from ivri_od.procurement.report.mandi_book.mandi_book import rst_net_qty

		self.net_qty = rst_net_qty(self.grn_note)
		keys = [(row.pass_unique_key or "").strip() for row in self.tp_rows]
		if not keys:
			frappe.throw(_("Add at least one TP No with its Qty."))
		if len(set(keys)) != len(keys):
			frappe.throw(_("A TP No is added more than once."))
		for row in self.tp_rows:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: enter the Qty of TP No {1}.").format(row.idx, row.transit_pass_no or row.pass_unique_key))
		total = flt(sum(flt(row.qty) for row in self.tp_rows), 3)
		if abs(total - flt(self.net_qty)) > TOLERANCE:
			frappe.throw(
				_("The Qty of the TP Nos adds up to {0} QT, but the RST Net Qty is {1} QT. They must be equal.").format(
					total, flt(self.net_qty, 3)
				)
			)
