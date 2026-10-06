# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import frappe
from frappe import _

from ivri_od.procurement.mill_gate import GATE_ENTRY_INSIDE_MILL


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Gate In"), "fieldname": "gate_entry", "fieldtype": "Link", "options": "Gate Entry", "width": 145},
		{"label": _("Vehicle No"), "fieldname": "vehicle_no", "fieldtype": "Data", "width": 125},
		{"label": _("Driver Name"), "fieldname": "driver_name", "fieldtype": "Data", "width": 150},
		{"label": _("Mobile No"), "fieldname": "mobile_no", "fieldtype": "Data", "width": 120},
		{"label": _("Entry Date"), "fieldname": "entry_date", "fieldtype": "Date", "width": 110},
		{"label": _("Entry Time"), "fieldname": "entry_time", "fieldtype": "Time", "width": 105},
		{"label": _("Exit Date"), "fieldname": "exit_date", "fieldtype": "Date", "width": 110},
		{"label": _("Exit Time"), "fieldname": "exit_time", "fieldtype": "Time", "width": 105},
		{"label": _("Gate Exit"), "fieldname": "gate_exit", "fieldtype": "Link", "options": "Gate Exit", "width": 145},
		{
			"label": _("Inside Mill"),
			"fieldname": "inside_mill",
			"fieldtype": "Data",
			"width": 95,
		},
	]


def get_data(filters):
	conditions = ["ge.in_out = 'In'"]
	values = {}
	entry_datetime = "COALESCE(ge.entry_datetime, TIMESTAMP(ge.entry_date, ge.entry_time))"
	if filters.get("from_date"):
		conditions.append(f"DATE({entry_datetime}) >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append(f"DATE({entry_datetime}) <= %(to_date)s")
		values["to_date"] = filters.to_date
	if filters.get("vehicle_no"):
		conditions.append("ge.vehicle_no LIKE %(vehicle_no)s")
		values["vehicle_no"] = f"%{filters.vehicle_no.strip()}%"

	mill_status = (filters.get("mill_status") or "").strip()
	if mill_status == "Inside Mill":
		conditions.append(f"({GATE_ENTRY_INSIDE_MILL})")
	elif mill_status == "Exited":
		conditions.append(f"NOT ({GATE_ENTRY_INSIDE_MILL})")

	return frappe.db.sql(
		f"""
		SELECT
			ge.name AS gate_entry,
			ge.vehicle_no,
			ge.driver_name,
			ge.mobile_no,
			DATE({entry_datetime}) AS entry_date,
			TIME({entry_datetime}) AS entry_time,
			gx.name AS gate_exit,
			DATE(gx.exit_datetime) AS exit_date,
			TIME(gx.exit_datetime) AS exit_time,
			IF(({GATE_ENTRY_INSIDE_MILL}), %(inside_yes)s, %(inside_no)s) AS inside_mill
		FROM `tabGate Entry` ge
		LEFT JOIN `tabGate Exit` gx ON gx.gate_entry_in = ge.name
		WHERE {' AND '.join(conditions)}
		ORDER BY {entry_datetime} DESC, ge.name DESC
		""",
		{**values, "inside_yes": _("Yes"), "inside_no": _("No")},
		as_dict=True,
	)
