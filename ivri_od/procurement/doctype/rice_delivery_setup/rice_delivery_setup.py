# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Rice due to FCI per rice type (Boiled / Raw), used by the DC Details report:
CMR % of the paddy, and driage % (Raw only)."""

from frappe.model.document import Document


class RiceDeliverySetup(Document):
	def validate(self):
		# Driage is taken only from raw paddy.
		if self.rice_type != "Raw":
			self.driage_percentage = 0
