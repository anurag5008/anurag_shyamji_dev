# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from ivri_od.procurement.portal_sync import build_record_name


class PortalRecord(Document):
	def autoname(self):
		if not (self.site and self.section and self.record_key):
			frappe.throw(_("Site, section and record key are required"))
		self.name = build_record_name(self.site, self.section, self.record_key, self.mill_id or "")
