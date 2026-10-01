# Copyright (c) 2026, Profezzo and contributors

import frappe
from frappe import _
from frappe.model.document import Document

from ivri_od.procurement.doctype.ppas_transit_pass.ppas_import import (
	import_manual_ppas_valid_rows,
	process_manual_ppas_paste,
)


class PPASTransitPassImport(Document):
	pass


@frappe.whitelist()
def process_paste(season, paste_data, miller=None):
	"""Stateless processing for new/unsaved import documents."""
	return process_manual_ppas_paste(season, paste_data, miller=miller)


@frappe.whitelist()
def import_valid_rows(season, items_json):
	return import_manual_ppas_valid_rows(season, items_json)
