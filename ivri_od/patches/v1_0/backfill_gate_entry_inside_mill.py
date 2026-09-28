"""Set Inside Mill on Gate Entry (In) from open visit rules."""

import frappe

from ivri_od.procurement.mill_gate import is_gate_in_inside_mill


def execute():
	if not frappe.db.has_column("Gate Entry", "inside_mill"):
		return

	for row in frappe.get_all("Gate Entry", filters={"in_out": "In"}, pluck="name"):
		inside = 1 if is_gate_in_inside_mill(row) else 0
		frappe.db.set_value("Gate Entry", row, "inside_mill", inside, update_modified=False)

	frappe.db.sql(
		"""
		UPDATE `tabGate Entry`
		SET inside_mill = 0
		WHERE in_out = 'Out'
		"""
	)
	frappe.db.commit()
