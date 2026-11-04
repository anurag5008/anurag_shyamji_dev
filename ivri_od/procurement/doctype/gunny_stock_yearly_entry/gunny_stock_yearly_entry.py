# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Values typed in the Gunny Stock Report Yearly by clicking a ✎ cell: one entry per mill, KMS Year,
District, month and column (Tr. Receipt, Tr. Issue, old bags procured / used, the costs)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_first_day, getdate


class GunnyStockYearlyEntry(Document):
	def validate(self):
		self.month = getdate(get_first_day(self.month))
		duplicate = frappe.db.exists(
			"Gunny Stock Yearly Entry",
			{
				"mill": self.mill,
				"kms_year": self.kms_year,
				"district": self.district,
				"month": self.month,
				"report_column": self.report_column,
				"name": ["!=", self.name],
			},
		)
		if duplicate:
			frappe.throw(_("A value for this month and column is already in {0}").format(duplicate))
