# Copyright (c) 2026, Profezzo and contributors
"""Mill Master: new "Display Name" and "Accounting Company" fields.

Display Name is filled from Company only where it is empty, so a rerun keeps edited values.
Accounting Company is left empty: the legal Companies are set up later."""

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "mill_master")
	for mill in frappe.get_all(
		"Mill Master",
		filters={"display_name": ["in", ["", None]], "company": ["is", "set"]},
		fields=["name", "company"],
	):
		frappe.db.set_value("Mill Master", mill.name, "display_name", mill.company, update_modified=False)
