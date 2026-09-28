"""Ensure Gunny Type select is on Weigh Bridge Measurement."""

import frappe


def execute():
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_measurement")
	frappe.clear_cache(doctype="Weigh Bridge Measurement")
