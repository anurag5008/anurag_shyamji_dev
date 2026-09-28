"""Add read-only Gate Entry link on Weigh Bridge Measurement."""

import frappe


def execute():
	frappe.reload_doc("Procurement", "doctype", "weigh_bridge_measurement", force=True)
