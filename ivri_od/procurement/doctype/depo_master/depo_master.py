# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class DepoMaster(Document):
	def validate(self):
		if self.code:
			self.code = self.code.strip().upper()
		if self.depo_name:
			self.depo_name = self.depo_name.strip()
		self.title = f"{self.depo_name} ({self.code})" if self.depo_name and self.code else ""
