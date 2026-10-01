# Copyright (c) 2026, Profezzo and contributors

from frappe.model.document import Document


class DistrictMaster(Document):
	def validate(self):
		if self.district_name:
			self.district_name = self.district_name.strip()
