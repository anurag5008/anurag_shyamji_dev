# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Stock by Physical Location.

Owner-wise rows: stock per operating unit (owner) inside each physical location, by item and season.
In a shared warehouse (a physical location and no operating unit) the owner is the operating unit of the batch;
in an older per-unit warehouse it is the unit of the warehouse.
Combined rows: the physical total of a location, adding the owners together once.
Each quantity sits in exactly one owner warehouse, so the combined total never counts stock twice.
Quantity is in the Item's stock UOM; bags come from the Bag Ledger and are shown beside it, not converted.
Batch-tracked items are read from Stock Ledger Entry + Serial and Batch Entry (as ERPNext does), other items from Bin.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

COMBINED = "Combined physical total"
UNATTRIBUTED = "(no operating unit on the batch)"
VIEW_OWNER_ONLY = "Owner-wise only"
VIEW_COMBINED_ONLY = "Combined physical only"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Physical Location"), "fieldname": "physical_location", "fieldtype": "Link", "options": "Physical Location", "width": 170},
		{"label": _("Owner (Operating Unit)"), "fieldname": "operating_unit", "fieldtype": "Data", "width": 190},
		{"label": _("Unit Type"), "fieldname": "unit_type", "fieldtype": "Data", "width": 80},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 200},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 170},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 130},
		{"label": _("Season"), "fieldname": "season", "fieldtype": "Link", "options": "Season Master", "width": 110},
		{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 150},
		{"label": _("Quantity"), "fieldname": "qty", "fieldtype": "Float", "precision": 3, "width": 110},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Data", "width": 70},
		{"label": _("Bags"), "fieldname": "bags", "fieldtype": "Int", "width": 80},
	]


def get_data(filters):
	warehouse_filters = {"physical_location": ["is", "set"], "is_group": 0}
	for key in ("physical_location", "company"):
		if filters.get(key):
			warehouse_filters[key] = filters[key]
	warehouses = frappe.get_all(
		"Warehouse",
		filters=warehouse_filters,
		fields=["name", "company", "operating_unit", "physical_location"],
		limit_page_length=0,
	)
	if not warehouses:
		return []
	names = [w.name for w in warehouses]
	items = {
		i.name: i
		for i in frappe.get_all("Item", fields=["name", "has_batch_no", "stock_uom"], limit_page_length=0)
	}
	balances = _batch_balances(names, items) + _bin_balances(names, items)
	batch_season = {
		b.name: (b.season or "")
		for b in frappe.get_all("Batch", fields=["name", "season"], limit_page_length=0)
	}
	bags = _bag_balances(names)
	unit_types = {m.name: m.type for m in frappe.get_all("Mill Master", fields=["name", "type"])}
	batch_unit = (
		{b.name: (b.operating_unit or "") for b in frappe.get_all("Batch", fields=["name", "operating_unit"], limit_page_length=0)}
		if frappe.db.has_column("Batch", "operating_unit")
		else {}
	)
	return build_rows(warehouses, balances, items, batch_season, bags, unit_types, filters, batch_unit)


def _batch_balances(warehouses, items):
	"""Batch quantity per warehouse, the way ERPNext reads it (serial_and_batch_bundle.get_available_batches):
	posted Stock Ledger Entries joined to their Serial and Batch Entries, cancelled ones left out, and a plain
	sum of the signed quantity (outward rows are stored negative). Disabled batches are kept: the stock is there."""
	rows = frappe.db.sql(
		"""
		select sbe.warehouse, sbe.item_code, sbe.batch_no, sum(sbe.qty) as qty
		from `tabStock Ledger Entry` sle
		join `tabSerial and Batch Entry` sbe on sbe.parent = sle.serial_and_batch_bundle
		where sle.is_cancelled = 0 and ifnull(sbe.batch_no, '') != ''
			and sbe.warehouse in %(warehouses)s
		group by sbe.warehouse, sbe.item_code, sbe.batch_no
		""",
		{"warehouses": warehouses},
		as_dict=True,
	)
	return [r for r in rows if flt(r.qty, 3) != 0]


def _bin_balances(warehouses, items):
	rows = frappe.db.sql(
		"select warehouse, item_code, actual_qty as qty from `tabBin` where warehouse in %(warehouses)s and actual_qty != 0",
		{"warehouses": warehouses},
		as_dict=True,
	)
	return [r for r in rows if not cint((items.get(r.item_code) or {}).get("has_batch_no"))]


def _bag_balances(warehouses):
	rows = frappe.db.sql(
		"""
		select warehouse, item_code, ifnull(batch_no, '') as batch_no, sum(bags) as bags
		from `tabBag Ledger Entry` where warehouse in %(warehouses)s
		group by warehouse, item_code, ifnull(batch_no, '')
		""",
		{"warehouses": warehouses},
		as_dict=True,
	)
	return {(r.warehouse, r.item_code, r.batch_no): cint(r.bags) for r in rows}


def build_rows(warehouses, balances, items, batch_season, bags, unit_types, filters, batch_unit=None) -> list[dict]:
	"""Owner-wise rows, plus one combined row per (location, item, season). Pure: no database access.

	batch_unit: operating unit of each batch, the owner of stock in a shared warehouse."""
	batch_unit = batch_unit or {}
	owner = {w.name: w for w in warehouses}
	view = filters.get("view") or ""
	rows = []
	for bal in balances:
		wh = owner.get(bal["warehouse"])
		if not wh:
			continue
		batch = bal.get("batch_no") or ""
		season = batch_season.get(batch, "") if batch else ""
		if filters.get("item_code") and bal["item_code"] != filters["item_code"]:
			continue
		if filters.get("season") and season != filters["season"]:
			continue
		item = items.get(bal["item_code"]) or {}
		owner_unit = wh.operating_unit or batch_unit.get(batch, "") or UNATTRIBUTED
		if filters.get("operating_unit") and owner_unit != filters["operating_unit"]:
			continue
		rows.append(
			{
				"physical_location": wh.physical_location,
				"operating_unit": owner_unit,
				"unit_type": unit_types.get(owner_unit, ""),
				"company": wh.company,
				"warehouse": wh.name,
				"item_code": bal["item_code"],
				"season": season,
				"batch_no": batch,
				"qty": flt(bal["qty"], 3),
				"uom": item.get("stock_uom") or "",
				"bags": cint(bags.get((wh.name, bal["item_code"], batch), 0)),
			}
		)
	rows.sort(key=lambda r: (r["physical_location"] or "", r["item_code"], r["season"], r["operating_unit"], r["batch_no"]))

	combined = {}
	for r in rows:
		key = (r["physical_location"], r["item_code"], r["season"])
		total = combined.setdefault(
			key,
			{
				"physical_location": r["physical_location"], "operating_unit": COMBINED, "unit_type": "",
				"company": "", "warehouse": "", "item_code": r["item_code"], "season": r["season"],
				"batch_no": "", "qty": 0.0, "uom": r["uom"], "bags": 0, "is_combined": 1,
			},
		)
		total["qty"] = flt(total["qty"] + r["qty"], 3)
		total["bags"] += r["bags"]

	if view == VIEW_COMBINED_ONLY:
		return sorted(combined.values(), key=lambda r: (r["physical_location"] or "", r["item_code"], r["season"]))
	if view == VIEW_OWNER_ONLY:
		return rows
	out = []
	for key in sorted(combined, key=lambda k: (k[0] or "", k[1], k[2])):
		out += [r for r in rows if (r["physical_location"], r["item_code"], r["season"]) == key]
		out.append(combined[key])
	return out
