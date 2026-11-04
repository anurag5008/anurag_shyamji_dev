# Copyright (c) 2026, Profezzo and contributors
"""Mill Reminder: add the two monthly reminders the client asked for (the roles are left empty on purpose: until they are chosen only System Managers see them).

Only these two records are added, and only if they do not exist."""

import frappe

REMINDERS = (
	("Electricity Bill and EPF", 2, "Reminder: Please pay the electricity bill and the EPF."),
	("Raw Mill Electricity Bill", 7, "Reminder: Please pay the electricity bill of the Raw Mill."),
)


def execute():
	for doctype in ("mill_reminder_role", "mill_reminder", "mill_reminder_completion"):
		frappe.reload_doc("procurement", "doctype", doctype)
	for title, day, message in REMINDERS:
		if frappe.db.exists("Mill Reminder", title):
			continue
		frappe.get_doc(
			{"doctype": "Mill Reminder", "reminder_title": title, "enabled": 1, "day_of_month": day, "visible_for_days": 3, "message": message}
		).insert(ignore_permissions=True)
