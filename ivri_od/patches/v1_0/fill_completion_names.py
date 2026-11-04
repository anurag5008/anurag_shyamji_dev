# Copyright (c) 2026, Profezzo and contributors
"""Mill Reminder Completion: fill in the names of Entered By and Approved By on records made before those name fields existed, so the list shows names.

Only the two display fields are written (the records are submitted, so nothing else is touched), and only where they are empty."""

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "mill_reminder_completion")
	for row in frappe.get_all("Mill Reminder Completion", fields=["name", "entered_by", "approved_by", "entered_by_name", "approved_by_name"]):
		values = {}
		for login, shown in (("entered_by", "entered_by_name"), ("approved_by", "approved_by_name")):
			if row.get(login) and not row.get(shown):
				values[shown] = frappe.db.get_value("User", row.get(login), "full_name") or row.get(login)
		if values:
			frappe.db.set_value("Mill Reminder Completion", row.name, values, update_modified=False)
