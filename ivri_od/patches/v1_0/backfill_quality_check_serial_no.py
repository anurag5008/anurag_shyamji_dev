"""Add QC Serial No to existing Quality Check records."""

import frappe
from frappe.utils import cint


def execute():
	if not frappe.db.has_column("Quality Check", "qc_serial_no"):
		return

	rows = frappe.get_all(
		"Quality Check",
		fields=["name", "qc_serial_no", "creation"],
		order_by="creation asc, name asc",
	)
	next_no = 1
	for row in rows:
		if cint(row.qc_serial_no):
			next_no = max(next_no, cint(row.qc_serial_no) + 1)
			continue
		frappe.db.set_value("Quality Check", row.name, "qc_serial_no", next_no, update_modified=False)
		next_no += 1

	frappe.db.commit()
