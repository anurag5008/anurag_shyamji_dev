# Copyright (c) 2026, Profezzo and contributors

"""Rice Dispatch: depot-wise dispatches from Weigh Bridge Measurement.

Source: Weigh Bridge Measurement records whose Status is Rice Dispatch (they are created from an RST
whose Party Name is a Depo Master Depo Name). Depot = Party Name, shown as the Depo Master Depo Name.
Quantity = Net Weight (QT), added up exactly as stored; nothing is converted.
The look follows the Entry Report (see the .js file).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate

RICE_DISPATCH_STATUS = "Rice Dispatch"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Depot Name"), "fieldname": "depot_name", "fieldtype": "Data", "width": 380},
		{"label": _("Number of Dispatches"), "fieldname": "dispatches", "fieldtype": "Int", "width": 190},
		{
			"label": _("Total Rice Dispatched (QT)"),
			"fieldname": "total_qt",
			"fieldtype": "Float",
			"precision": 3,
			"width": 240,
		},
	]


def _name_key(name) -> str:
	"""Case and extra spaces do not matter, as in the RST depot match."""
	return " ".join((name or "").split()).casefold()


def build_query(filters) -> tuple[str, dict]:
	"""Rice Dispatch weighments inside the date range (both dates included)."""
	conditions = ["`tp_status` = %(status)s", "`docstatus` < 2"]
	values = {"status": RICE_DISPATCH_STATUS}
	if filters.get("from_date"):
		conditions.append("date(`date`) >= %(from_date)s")
		values["from_date"] = getdate(filters.from_date)
	if filters.get("to_date"):
		conditions.append("date(`date`) <= %(to_date)s")
		values["to_date"] = getdate(filters.to_date)
	query = (
		"select `name`, `party_name`, `net_weight` from `tabWeigh Bridge Measurement` "
		f"where {' and '.join(conditions)} order by `date`"
	)
	return query, values


def _depot_filter_key(depot) -> str:
	"""The Depot Name filter is a Depo Master (its code) or a typed depot name."""
	depot = (depot or "").strip()
	if not depot:
		return ""
	if frappe.db.exists("Depo Master", depot):
		depot = frappe.db.get_value("Depo Master", depot, "depo_name") or depot
	return _name_key(depot)


def _depos() -> dict[str, dict]:
	"""Depo Master name (code) and Depo Name by lower-case Depo Name, oldest record first."""
	depos: dict[str, dict] = {}
	for row in frappe.db.sql("select `name`, `depo_name` from `tabDepo Master` order by `creation`", as_dict=True):
		depos.setdefault(
			_name_key(row.depo_name), {"code": row.name, "depo_name": " ".join(row.depo_name.split())}
		)
	return depos


def get_data(filters):
	filters = frappe._dict(filters or {})
	if filters.get("from_date") and filters.get("to_date") and getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date."))

	query, values = build_query(filters)
	records = frappe.db.sql(query, values, as_dict=True)
	depos = _depos()
	wanted = _depot_filter_key(filters.get("depot_name"))

	groups: dict[str, dict] = {}
	for record in records:
		party = " ".join((record.party_name or "").split())
		key = _name_key(party)
		if wanted and key != wanted:
			continue
		depo = depos.get(key)
		group = groups.setdefault(
			key,
			{
				"depot_name": depo["depo_name"] if depo else party or _("(No Depot Name)"),
				# not a column: lets the Depot Name open its Depo Master
				"depot_code": depo["code"] if depo else "",
				"dispatches": 0,
				"total_qt": 0.0,
			},
		)
		group["dispatches"] += 1
		group["total_qt"] = flt(group["total_qt"] + flt(record.net_weight), 3)

	return sorted(groups.values(), key=lambda row: row["depot_name"].casefold())
