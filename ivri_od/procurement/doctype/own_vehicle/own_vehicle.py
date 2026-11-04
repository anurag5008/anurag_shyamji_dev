# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from ivri_od.procurement.vehicle_statement import normal_vehicle


class OwnVehicle(Document):
	def validate(self):
		self.vehicle_no = normal_vehicle(self.vehicle_no)  # capitals and no spaces, as the PPAS passes write it
