"""Rename PPAS Transit Pass rows so document name equals pass_unique_key (safe to re-run)."""

from __future__ import annotations

import frappe


def execute():
	rename_all_ppas_to_pass_unique_key()
	frappe.db.commit()


def rename_all_ppas_to_pass_unique_key():
	if not frappe.db.table_exists("tabPPAS Transit Pass"):
		return

	rows = frappe.db.sql(
		"""
		SELECT name, pass_unique_key
		FROM `tabPPAS Transit Pass`
		WHERE IFNULL(pass_unique_key, '') != ''
		ORDER BY creation
		""",
		as_dict=True,
	)

	renamed = 0
	skipped = 0
	for row in rows:
		key = (row.pass_unique_key or "").strip()
		if not key or row.name == key:
			continue
		if frappe.db.exists("PPAS Transit Pass", key):
			skipped += 1
			continue
		frappe.rename_doc("PPAS Transit Pass", row.name, key, force=True, merge=False)
		renamed += 1

	frappe.logger().info(
		f"PPAS rename to pass_unique_key: renamed={renamed}, skipped={skipped}, total={len(rows)}"
	)

	_fix_weigh_bridge_pass_unique_keys()


def _fix_weigh_bridge_pass_unique_keys():
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
		stored = (row.pass_unique_key or "").strip()
		if not stored:
			continue
		if frappe.db.exists("PPAS Transit Pass", {"pass_unique_key": stored}):
			continue
		key = frappe.db.get_value("PPAS Transit Pass", stored, "pass_unique_key")
		if key and key != stored:
			frappe.db.set_value(
				"Weigh Bridge Measurement",
				row.name,
				"pass_unique_key",
				key,
				update_modified=False,
			)
