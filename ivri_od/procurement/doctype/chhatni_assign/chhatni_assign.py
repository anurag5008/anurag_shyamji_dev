# Copyright (c) 2026, Profezzo and contributors

from frappe.model.document import Document
from frappe.utils import flt


class ChhatniAssign(Document):
	def validate(self):
		kg = flt(self.chutney_quantity_kg_per_quintal)
		self.chutney_quantity_kg_per_quintal = kg
		# 1 quintal = 100 kg → kg per quintal equals percentage of total weight
		self.chutney_percentage = kg
