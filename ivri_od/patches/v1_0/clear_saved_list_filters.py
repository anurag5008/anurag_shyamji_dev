# Copyright (c) 2026, Profezzo and contributors
"""RST Details, Weigh Bridge Measurement and PPAS Transit Pass lists open with no filter.

Frappe remembers the filters used last time for every user, so these lists opened already filtered
(for example PPC like kanut). The saved filters and the sidebar group-by of these three lists are cleared."""

import json

import frappe

DOCTYPES = ("RST Details", "Weigh Bridge Measurement", "PPAS Transit Pass")


def execute():
	rows = frappe.db.sql(
		"SELECT `user`, `doctype`, `data` FROM `__UserSettings` WHERE `doctype` IN %s", (DOCTYPES,), as_dict=True
	)
	for row in rows:
		try:
			data = json.loads(row.data or "{}")
		except ValueError:
			continue
		for view in ("List", "Report", "Kanban", "Gantt", "Calendar"):
			if isinstance(data.get(view), dict):
				data[view]["filters"] = []
		data.pop("group_by_fields", None)
		frappe.db.sql(
			"UPDATE `__UserSettings` SET `data` = %s WHERE `user` = %s AND `doctype` = %s",
			(json.dumps(data), row.user, row.doctype),
		)
	frappe.clear_cache()
