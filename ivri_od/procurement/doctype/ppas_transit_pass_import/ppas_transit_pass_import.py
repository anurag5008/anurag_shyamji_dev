# Copyright (c) 2026, Profezzo and contributors

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr

from ivri_od.procurement.doctype.ppas_transit_pass.ppas_import import (
	import_manual_ppas_valid_rows,
	manual_item_from_import_child,
	process_manual_ppas_paste,
)


class PPASTransitPassImport(Document):
	def validate(self):
		"""Saving never creates PPAS Transit Pass rows — use Push button on the form."""
		pass


def _apply_process_result(doc, result):
	doc.import_items = []
	for row in result.get("items") or []:
		doc.append("import_items", row)

	doc.total_records = cint(result.get("total_records"))
	doc.duplicate_records = cint(result.get("duplicate_records"))
	doc.failed_records = cint(result.get("failed_records"))


@frappe.whitelist()
def process_paste(season, paste_data, miller=None):
	"""Parse/validate paste only (no document update)."""
	return process_manual_ppas_paste(season, paste_data, miller=miller)


@frappe.whitelist()
def process_and_save_import(name=None, season=None, paste_data=None, miller=None):
	"""Parse pasted data, fill child table, and save this import document."""
	if not season:
		frappe.throw(_("Season is required"))
	if not paste_data or not cstr(paste_data).strip():
		frappe.throw(_("Paste PPAS data before processing"))

	if name and frappe.db.exists("PPAS Transit Pass Import", name):
		doc = frappe.get_doc("PPAS Transit Pass Import", name)
		doc.season = season
		doc.paste_data = paste_data
	else:
		doc = frappe.new_doc("PPAS Transit Pass Import")
		doc.season = season
		doc.paste_data = paste_data

	result = process_manual_ppas_paste(doc.season, doc.paste_data, miller=getattr(doc, "miller", miller))
	if not result.get("items"):
		frappe.throw(_("No PPAS rows found in pasted data"))

	_apply_process_result(doc, result)
	doc.save()

	return {
		"name": doc.name,
		"total_records": doc.total_records,
		"duplicate_records": doc.duplicate_records,
		"failed_records": doc.failed_records,
		"item_count": len(doc.import_items),
	}


@frappe.whitelist()
def push_valid_to_transit_pass(name):
	"""Create/update PPAS Transit Pass only when user clicks Push (not on save)."""
	if not name or not frappe.db.exists("PPAS Transit Pass Import", name):
		frappe.throw(_("Save and process this import first"))

	doc = frappe.get_doc("PPAS Transit Pass Import", name)
	valid_items = [
		manual_item_from_import_child(row)
		for row in doc.import_items
		if getattr(row, "row_status", None) in (None, "", "Valid")
	]
	if not valid_items:
		frappe.throw(_("No rows to push. Check Import Items."))

	import_result = import_manual_ppas_valid_rows(doc.season, valid_items)

	if doc.paste_data:
		result = process_manual_ppas_paste(doc.season, doc.paste_data, getattr(doc, "miller", None))
		_apply_process_result(doc, result)
		doc.save()

	return import_result


@frappe.whitelist()
def import_valid_rows(season, items_json):
	return import_manual_ppas_valid_rows(season, items_json)
