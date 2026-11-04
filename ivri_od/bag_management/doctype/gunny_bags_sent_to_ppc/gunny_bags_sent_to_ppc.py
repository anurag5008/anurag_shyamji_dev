# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Miller-owned gunny bags sent to a PPC: date, operating unit, PPC, district (from the PPC) and the number of bags."""

import frappe
from frappe import _
from frappe.model.document import Document


def bag_count_error(value) -> str | None:
	"""The number of bags must be a whole number above zero."""
	try:
		number = float(value)
	except (TypeError, ValueError):
		return _("Number of Bags Sent must be a number.")
	if number != int(number):
		return _("Number of Bags Sent must be a whole number.")
	if int(number) <= 0:
		return _("Number of Bags Sent must be more than zero.")
	return None


class GunnyBagsSenttoPPC(Document):
	def validate(self):
		error = bag_count_error(self.bags_sent)
		if error:
			frappe.throw(error)
