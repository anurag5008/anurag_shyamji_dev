# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class MillReminderCompletion(Document):
	"""A reminder marked as completed: the bank, the amount, who entered it and who approved it, with the date and time filled in by the system.
	It is submitted, so it cannot be changed afterwards (a System Manager can cancel it, and the reminder then shows again)."""

	def validate(self):
		if not self.is_new():
			return
		for fieldname, label in (("bank", "Bank"), ("entered_by", "Entered By"), ("approved_by", "Approved By")):
			if not (self.get(fieldname) or "").strip():
				frappe.throw(_("{0} is required.").format(_(label)))
		if not frappe.db.exists("Bank", self.bank.strip()):
			frappe.throw(_("Choose the bank from the list. A bank that is not in the list has to be added to the Bank list first."))
		if flt(self.amount) <= 0:
			frappe.throw(_("Amount must be more than 0."))
		for fieldname, label in (("entered_by", "Entered By"), ("approved_by", "Approved By")):
			user = frappe.db.get_value("User", self.get(fieldname), ["enabled", "full_name"], as_dict=True)
			if not user or not user.enabled:
				frappe.throw(_("{0} must be an active user.").format(_(label)))
			self.set(f"{fieldname}_name", user.full_name or self.get(fieldname))  # the list shows the name the client knows, not the login
		self.bank = self.bank.strip()
		self.completed_on = now_datetime()  # always filled in by the system, whatever the screen sent
		self.completed_by = frappe.session.user
