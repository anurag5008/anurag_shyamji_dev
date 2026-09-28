"""Rename PPAS Transit Pass document names to pass_unique_key for Link fields."""

from __future__ import annotations

import frappe


def execute():
	if not frappe.db.table_exists("tabPPAS Transit Pass"):
		return

	rows = frappe.db.sql(
		"""
		SELECT name, pass_unique_key
		FROM `tabPPAS Transit Pass`
		WHERE IFNULL(pass_unique_key, '') != ''
		""",
		as_dict=True,
	)

	for row in rows:
		key = (row.pass_unique_key or "").strip()
		if not key or row.name == key:
			continue
		if frappe.db.exists("PPAS Transit Pass", key):
			frappe.log_error(
				title="PPAS rename skipped (target exists)",
				message=f"Cannot rename {row.name} to {key}",
			)
			continue
		frappe.rename_doc("PPAS Transit Pass", row.name, key, force=True, merge=False)

	_migrate_weigh_bridge_links()
	frappe.db.commit()


def _migrate_weigh_bridge_links():
	if not frappe.db.table_exists("tabWeigh Bridge Measurement"):
		return

	for row in frappe.db.sql(
		"""
		SELECT name, pass_unique_key
		FROM `tabWeigh Bridge Measurement`
		WHERE IFNULL(pass_unique_key, '') != ''
		""",
		as_dict=True,
	):
		key = (row.pass_unique_key or "").strip()
		if not key:
			continue
		if frappe.db.exists("PPAS Transit Pass", key):
			continue
		resolved = frappe.db.get_value(
			"PPAS Transit Pass", {"pass_unique_key": key}, "name"
		)
		if resolved and resolved != key:
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				row.name,
				"pass_unique_key",
				resolved,
				update_modified=False,
			)
