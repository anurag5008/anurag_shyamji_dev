# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class PhysicalLocation(Document):
	def validate(self):
		self.location_name = (self.location_name or "").strip()
