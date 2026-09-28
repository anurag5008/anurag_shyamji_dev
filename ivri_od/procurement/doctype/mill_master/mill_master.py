# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MillMaster(Document):
	def validate(self):
		if self.miller_code:
			self.miller_code = self.miller_code.strip().upper()
