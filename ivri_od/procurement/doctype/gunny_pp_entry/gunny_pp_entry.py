# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""PP bags of the New NBT Gunny Account, typed in the report by clicking a PP cell: one entry
per mill, KMS Year, month and account (Receipts, Other, or Issue of a District)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_first_day, getdate


class GunnyPPEntry(Document):
	def validate(self):
		self.month = getdate(get_first_day(self.month))
		if self.account != "Issue":
			self.district = None
		elif not self.district:
			frappe.throw(_("Select the District of this Issue"))
		duplicate = frappe.db.exists(
			"Gunny PP Entry",
			{
				"mill": self.mill,
				"kms_year": self.kms_year,
				"month": self.month,
				"account": self.account,
				"district": self.district or ("is", "not set"),
				"name": ["!=", self.name],
			},
		)
		if duplicate:
			frappe.throw(_("PP bags for this month and account are already in {0}").format(duplicate))
