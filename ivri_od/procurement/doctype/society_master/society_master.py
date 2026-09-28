# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class SocietyMaster(Document):
	def validate(self):
		if self.code:
			self.code = self.code.strip().upper()
		if self.ppc_name:
			self.ppc_name = self.ppc_name.strip()
