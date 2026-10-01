"""Remove duplicate Client Scripts so only gate_entry.js controls pass buttons."""

import frappe


def execute():
	for name in ("Gate Entry Pass Toolbar", "Gate Exit Pass Toolbar"):
		if frappe.db.exists("Client Script", name):
			frappe.delete_doc("Client Script", name, force=True)

	frappe.reload_doc("procurement", "doctype", "gate_entry")
	frappe.clear_cache(doctype="Gate Entry")
