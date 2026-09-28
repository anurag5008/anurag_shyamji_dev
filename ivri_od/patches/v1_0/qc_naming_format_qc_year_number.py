"""Quality Check naming: QC-2026-1 instead of QC-2026-00001."""

import frappe
from frappe.model.rename_doc import rename_doc


def execute():
	old_name = "QC-2026-00001"
	new_name = "QC-2026-1"

	if frappe.db.exists("Quality Check", old_name) and not frappe.db.exists("Quality Check", new_name):
		rename_doc("Quality Check", old_name, new_name, force=True, merge=False)

	prefix = "QC-2026-"
	if frappe.db.exists("Series", prefix):
		frappe.db.set_value("Series", prefix, "current", 1, update_modified=False)
	else:
		frappe.db.sql(
			"INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)",
			(prefix, 1),
		)

	frappe.db.commit()
