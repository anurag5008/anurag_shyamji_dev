# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MillReminder(Document):
	def validate(self):
		if not 1 <= int(self.day_of_month or 0) <= 31:
			frappe.throw(_("Day of Month must be between 1 and 31."))
		if int(self.visible_for_days or 0) < 1:
			frappe.throw(_("Visible for (Days) must be at least 1."))
