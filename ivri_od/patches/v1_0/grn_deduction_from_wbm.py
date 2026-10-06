"""Copy deduction (QT) from linked weigh bridge onto GRN Note."""

import frappe
from frappe.utils import flt


def execute():
	rows = frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2]},
		fields=["name", "weigh_bridge_measurement"],
	)
	for row in rows:
		wbm_name = (row.weigh_bridge_measurement or "").strip()
		if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
			continue
		deduction = flt(frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "deduction"))
		frappe.db.set_value("GRN Note", row.name, "deduction", deduction, update_modified=False)
