# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document

from ivri_od.procurement.datetime_fields import ensure_doc_datetime
from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import make_pass_unique_key
from ivri_od.procurement.doctype.ppas_transit_pass.ppas_import import split_datetime


class PPASTransitPass(Document):
	def before_insert(self):
		self.set_pass_unique_key()

	def before_validate(self):
		self.split_datetime_fields()

	def validate(self):
		if self.transit_pass_no:
			self.transit_pass_no = self.transit_pass_no.strip()
		if self.ppc:
			self.ppc = self.ppc.strip()
		if self.miller:
			self.miller = self.miller.strip()

		self.set_pass_unique_key()
		ensure_doc_datetime(
			self,
			"transit_pass_datetime",
			date_field="transit_pass_date",
			time_field="transit_pass_time",
		)
		ensure_doc_datetime(
			self,
			"accepted_datetime",
			date_field="accepted_date",
			time_field="accepted_time",
		)
		self.validate_duplicate_identity()
		self.validate_duplicate_pass_unique_key()

	def set_pass_unique_key(self):
		if not (self.transit_pass_no and self.ppc and self.season):
			return
		self.pass_unique_key = make_pass_unique_key(
			self.transit_pass_no, self.ppc, self.miller, self.season
		)

	def split_datetime_fields(self):
		for date_field, time_field in (
			("transit_pass_date", "transit_pass_time"),
			("accepted_date", "accepted_time"),
		):
			raw_value = self.get(date_field)
			if not raw_value:
				continue

			date_value, time_value = split_datetime(raw_value)
			if date_value:
				self.set(date_field, date_value)
			if time_value:
				self.set(time_field, time_value)

	def validate_duplicate_identity(self):
		"""Duplicate identity is Season + PPC + Transit Pass No.

		Transit Pass No alone is NOT unique.
		"""
		if not (self.season and self.ppc and self.transit_pass_no):
			return

		existing = frappe.db.exists(
			"PPAS Transit Pass",
			{
				"season": self.season,
				"ppc": self.ppc,
				"transit_pass_no": self.transit_pass_no,
				"name": ("!=", self.name),
			},
		)
		if existing:
			frappe.throw(
				frappe._(
					"Duplicate PPAS Transit Pass: Season {0}, PPC {1}, Transit Pass No {2} already exists ({3})"
				).format(self.season, self.ppc, self.transit_pass_no, existing)
			)

	def validate_duplicate_pass_unique_key(self):
		if not self.pass_unique_key:
			return

		existing = frappe.db.exists(
			"PPAS Transit Pass",
			{
				"pass_unique_key": self.pass_unique_key,
				"name": ("!=", self.name),
			},
		)
		if existing:
			frappe.throw(
				frappe._("Duplicate Pass Unique Key {0} already exists ({1})").format(
					self.pass_unique_key, existing
				)
			)


def _ensure_list_view_settings():
	"""List: Sl# first, then Transit Pass No, bag/delay, etc."""
	doctype = "PPAS Transit Pass"
	preferred_order = [
		"sl",
		"transit_pass_no",
		"pass_unique_key",
		"season",
		"ppc",
		"miller",
		"bags",
		"delay_in_days",
		"quantity",
	]

	if frappe.db.exists("List View Settings", doctype):
		doc = frappe.get_doc("List View Settings", doctype)
		stored = json.loads(doc.fields or "[]")
	else:
		doc = frappe.new_doc("List View Settings")
		doc.name = doctype
		stored = []

	by_name = {
		item.get("fieldname"): item
		for item in stored
		if isinstance(item, dict) and item.get("fieldname")
	}

	fields = []
	for fieldname in preferred_order:
		fields.append(by_name.get(fieldname) or {"fieldname": fieldname})

	for fieldname, item in by_name.items():
		if fieldname not in preferred_order:
			fields.append(item)

	doc.fields = json.dumps(fields)
	doc.flags.ignore_permissions = True
	if doc.get("__islocal"):
		doc.insert()
	else:
		doc.save()


@frappe.whitelist()
def delete_all_transit_passes():
	frappe.only_for("System Manager")

	count = frappe.db.count("PPAS Transit Pass")
	if not count:
		return {"deleted": 0, "message": "No PPAS Transit Pass records to delete."}

	frappe.db.delete("PPAS Transit Pass")
	frappe.db.commit()

	return {
		"deleted": count,
		"message": f"Deleted {count} PPAS Transit Pass record(s).",
	}


def on_doctype_update():
	frappe.db.add_unique(
		"PPAS Transit Pass",
		["season", "ppc", "transit_pass_no"],
		constraint_name="unique_season_ppc_transit_pass_no",
	)
	frappe.db.add_unique(
		"PPAS Transit Pass",
		["pass_unique_key"],
		constraint_name="unique_pass_unique_key",
	)
	_ensure_list_view_settings()
