# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Track vehicles inside the mill (Gate In without matching Gate Out)."""

from __future__ import annotations

import frappe
from frappe.utils import cint

GATE_IN_INSIDE_MILL = """
NOT EXISTS (
	SELECT 1
	FROM `tabGate Entry` ge_out
	WHERE ge_out.in_out = 'Out'
		AND ge_out.gate_entry_in = ge_in.name
)
AND NOT EXISTS (
	SELECT 1
	FROM `tabGate Exit` gx
	WHERE gx.gate_entry_in = ge_in.name
)
"""

# Same rule when the open Gate In row uses alias `ge`.
GATE_ENTRY_INSIDE_MILL = """
NOT EXISTS (
	SELECT 1
	FROM `tabGate Entry` ge_out
	WHERE ge_out.in_out = 'Out'
		AND ge_out.gate_entry_in = ge.name
)
AND NOT EXISTS (
	SELECT 1
	FROM `tabGate Exit` gx
	WHERE gx.gate_entry_in = ge.name
)
"""


def normalize_vehicle_no(vehicle_no: str | None) -> str:
	return (vehicle_no or "").strip().upper()


def is_gate_in_inside_mill(gate_entry_in: str) -> bool:
	gate_entry_in = (gate_entry_in or "").strip()
	if not gate_entry_in or not frappe.db.exists("Gate Entry", gate_entry_in):
		return False
	if frappe.db.get_value("Gate Entry", gate_entry_in, "in_out") != "In":
		return False
	return not frappe.db.exists(
		"Gate Entry", {"in_out": "Out", "gate_entry_in": gate_entry_in}
	) and not frappe.db.exists("Gate Exit", {"gate_entry_in": gate_entry_in})


def get_open_gate_entry_in_for_vehicle(
	vehicle_no: str, exclude_in: str | None = None
) -> str | None:
	vehicle_no = normalize_vehicle_no(vehicle_no)
	if not vehicle_no:
		return None

	exclude_sql = ""
	values: list = [vehicle_no]
	if (exclude_in or "").strip():
		exclude_sql = "AND ge_in.name != %s"
		values.append(exclude_in.strip())

	rows = frappe.db.sql(
		f"""
		SELECT ge_in.name
		FROM `tabGate Entry` ge_in
		WHERE ge_in.in_out = 'In'
			AND UPPER(TRIM(ge_in.vehicle_no)) = %s
			AND {GATE_IN_INSIDE_MILL}
			{exclude_sql}
		ORDER BY ge_in.entry_date DESC, ge_in.entry_time DESC, ge_in.creation DESC
		LIMIT 1
		""",
		tuple(values),
		pluck=True,
	)
	return rows[0] if rows else None


def get_weighment_vehicle_from_gate_entry(truck_no_in_tp: str | None = None) -> str | None:
	"""Vehicle on open Gate In marked Going to Weighment (still inside mill)."""
	truck_no_in_tp = normalize_vehicle_no(truck_no_in_tp)
	values: list = []

	if truck_no_in_tp:
		row = frappe.db.sql(
			f"""
			SELECT UPPER(TRIM(ge_in.vehicle_no)) AS vehicle_no
			FROM `tabGate Entry` ge_in
			WHERE ge_in.in_out = 'In'
				AND ge_in.going_to_weighment = 1
				AND UPPER(TRIM(ge_in.vehicle_no)) = %s
				AND {GATE_IN_INSIDE_MILL}
			ORDER BY ge_in.entry_date DESC, ge_in.entry_time DESC, ge_in.creation DESC
			LIMIT 1
			""",
			truck_no_in_tp,
			as_dict=True,
		)
		if row:
			return row[0].vehicle_no

	rows = frappe.db.sql(
		f"""
		SELECT UPPER(TRIM(ge_in.vehicle_no)) AS vehicle_no
		FROM `tabGate Entry` ge_in
		WHERE ge_in.in_out = 'In'
			AND ge_in.going_to_weighment = 1
			AND IFNULL(ge_in.vehicle_no, '') != ''
			AND {GATE_IN_INSIDE_MILL}
		ORDER BY ge_in.entry_date DESC, ge_in.entry_time DESC, ge_in.creation DESC
		LIMIT 1
		""",
		as_dict=True,
	)
	return rows[0].vehicle_no if rows else None


def get_weighment_vehicles_inside_mill(txt: str = "", limit: int = 25) -> list[str]:
	"""Distinct vehicles on open Gate In with Going to Weighment."""
	txt = normalize_vehicle_no(txt)
	limit = cint(limit) or 25
	conditions = [
		"ge_in.in_out = 'In'",
		"ge_in.going_to_weighment = 1",
		"IFNULL(ge_in.vehicle_no, '') != ''",
		GATE_IN_INSIDE_MILL,
	]
	values: list = []
	if txt:
		conditions.append("UPPER(TRIM(ge_in.vehicle_no)) LIKE %s")
		values.append(f"%{txt}%")
	values.append(limit)

	return frappe.db.sql(
		f"""
		SELECT DISTINCT UPPER(TRIM(ge_in.vehicle_no)) AS vehicle_no
		FROM `tabGate Entry` ge_in
		WHERE {" AND ".join(conditions)}
		ORDER BY vehicle_no
		LIMIT %s
		""",
		tuple(values),
		pluck=True,
	)


def get_qc_for_vehicle_open_visit(vehicle_no: str) -> dict | None:
	vehicle_no = normalize_vehicle_no(vehicle_no)
	if not vehicle_no:
		return None

	rows = frappe.db.sql(
		f"""
		SELECT qc.name, qc.vehicle_no, qc.gate_entry, qc.qc_decision
		FROM `tabQuality Check` qc
		INNER JOIN `tabGate Entry` ge_in ON ge_in.name = qc.gate_entry
		WHERE ge_in.in_out = 'In'
			AND UPPER(TRIM(qc.vehicle_no)) = %s
			AND {GATE_IN_INSIDE_MILL}
		ORDER BY qc.modified DESC, qc.creation DESC
		LIMIT 1
		""",
		vehicle_no,
		as_dict=True,
	)
	return rows[0] if rows else None


def get_quality_check_for_vehicle_open_visit(vehicle_no: str) -> str | None:
	qc = get_qc_for_vehicle_open_visit(vehicle_no)
	return qc.name if qc else None


def get_qc_sl_no(qc_name: str | None) -> int:
	"""Serial number for mapping WBM ↔ QC (qc_serial_no or QC-YYYY-N suffix)."""
	qc_name = (qc_name or "").strip()
	if not qc_name or not frappe.db.exists("Quality Check", qc_name):
		return 0

	serial = cint(frappe.db.get_value("Quality Check", qc_name, "qc_serial_no"))
	if serial:
		return serial

	if qc_name.startswith("QC-"):
		tail = qc_name.rsplit("-", 1)[-1]
		if tail.isdigit():
			return cint(tail)
	return 0


def get_qc_serial_for_vehicle(vehicle_no: str) -> int:
	qc = get_qc_for_vehicle_open_visit(vehicle_no)
	return get_qc_sl_no(qc.name) if qc else 0


def get_vehicles_inside_mill(txt: str = "", limit: int = 25) -> list[str]:
	txt = normalize_vehicle_no(txt)
	limit = cint(limit) or 25
	values: list = []
	conditions = [
		"ge_in.in_out = 'In'",
		"IFNULL(ge_in.vehicle_no, '') != ''",
		GATE_IN_INSIDE_MILL,
	]
	if txt:
		conditions.append("UPPER(TRIM(ge_in.vehicle_no)) LIKE %s")
		values.append(f"%{txt}%")
	values.append(limit)

	return frappe.db.sql(
		f"""
		SELECT DISTINCT UPPER(TRIM(ge_in.vehicle_no)) AS vehicle_no
		FROM `tabGate Entry` ge_in
		WHERE {" AND ".join(conditions)}
		ORDER BY vehicle_no
		LIMIT %s
		""",
		tuple(values),
		pluck=True,
	)
