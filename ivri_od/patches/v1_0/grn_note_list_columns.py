# Copyright (c) 2026, Profezzo and contributors
"""GRN Note list: the columns in the order staff read them (Date & Time first, PPC and Mill after the vehicle)."""

import json

import frappe

DOCTYPE = "GRN Note"
ORDER = [
	"receipt_datetime",
	"rst_no",
	"transit_pass_no",
	"vehicle_no",
	"ppc",
	"mill_name",
	"net_weight",
	"tp_fulfillment_status",
	"chhatni_fulfillment_status",
]


def execute():
	meta = frappe.get_meta(DOCTYPE)
	fields = json.dumps([{"fieldname": n, "label": meta.get_label(n)} for n in ORDER])
	if frappe.db.exists("List View Settings", DOCTYPE):
		settings = frappe.get_doc("List View Settings", DOCTYPE)
		settings.fields = fields
		settings.save(ignore_permissions=True)
	else:
		settings = frappe.new_doc("List View Settings")
		settings.name = DOCTYPE
		settings.fields = fields
		settings.insert(ignore_permissions=True)
	frappe.clear_cache(doctype=DOCTYPE)
