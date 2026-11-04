# Copyright (c) 2026, Profezzo and contributors
"""Show the DocType "Miller Verification Report" as "PVR" in list, form and breadcrumb titles.

Only the shown text changes: a Translation for the English language. The DocType name stays "Miller Verification
Report", so links, permissions, records and code are untouched. The text is unique to this DocType, so nothing else
is renamed. Safe to run again."""

import frappe

SOURCE = "Miller Verification Report"
TARGET = "PVR"


def execute():
	existing = frappe.db.get_value("Translation", {"language": "en", "source_text": SOURCE, "context": ["in", ["", None]]}, "name")
	if existing:
		frappe.db.set_value("Translation", existing, "translated_text", TARGET)
	else:
		frappe.get_doc(
			{"doctype": "Translation", "language": "en", "source_text": SOURCE, "translated_text": TARGET}
		).insert(ignore_permissions=True)
	frappe.clear_cache()
