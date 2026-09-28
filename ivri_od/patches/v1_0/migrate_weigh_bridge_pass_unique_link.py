"""Copy legacy transit_pass Link to pass_unique_key before field is removed."""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.table_exists("tabWeigh Bridge Measurement"):
		return
	if not frappe.db.has_column("Weigh Bridge Measurement", "transit_pass"):
		return

	for row in frappe.db.sql(
		"""
		SELECT name, transit_pass, pass_unique_key
		FROM `tabWeigh Bridge Measurement`
		WHERE IFNULL(transit_pass, '') != ''
		""",
		as_dict=True,
	):
		if row.pass_unique_key:
			continue
		key = frappe.db.get_value(
			"PPAS Transit Pass", row.transit_pass, "pass_unique_key"
		) or row.transit_pass
		if key:
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				row.name,
				"pass_unique_key",
				key,
				update_modified=False,
			)

	frappe.db.commit()
