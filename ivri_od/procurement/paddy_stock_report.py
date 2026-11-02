# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Warehouse Wise Stock Balance (ERPNext): the "Stock Balance" column becomes "Paddy Stock".

Paddy Stock of a warehouse = the total Net Weight (QT) of the GRN Notes whose Quality Check (GRN field QC Sample No)
names that warehouse as its Unloading Point. All GRN Notes count, each once, grouped by warehouse. ERPNext's own report
code then fills the tree: a group warehouse shows the sum of its children.

ERPNext is not edited. Two small functions of its report module are replaced at runtime, only for this report:
- get_warehouse_wise_balance: the quantity per warehouse comes from the GRN Notes instead of the Stock Ledger;
- get_columns: the label of the stock_balance column.
install() is idempotent and is called by Frappe's before_request and before_job hooks (hooks.py); uninstall() restores
ERPNext's own functions. An Unloading Point that is not a Warehouse (older Quality Checks hold free text) matches no
warehouse and is not counted. Nothing is deducted: there is no record of paddy leaving a warehouse.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt

REPORT_MODULE = "erpnext.stock.report.warehouse_wise_stock_balance.warehouse_wise_stock_balance"
LABEL = "Paddy Stock"
_MARK = "_ivri_od_paddy_stock"


def paddy_stock_query():
	"""One row per Unloading Point: the warehouse and the total GRN Net Weight (QT). Each GRN Note is one row of the
	join (it has one Quality Check), so nothing is counted twice."""
	grn = frappe.qb.DocType("GRN Note")
	qc = frappe.qb.DocType("Quality Check")
	return (
		frappe.qb.from_(grn)
		.join(qc)
		.on(qc.name == grn.quality_check)
		.select(qc.unloading_point, Sum(grn.net_weight))
		.where((grn.docstatus < 2) & qc.unloading_point.isnotnull() & (qc.unloading_point != ""))
		.groupby(qc.unloading_point)
	)


def get_paddy_stock_by_warehouse(filters=None) -> dict:
	"""{warehouse: total Net Weight (QT)}. The report lists the warehouses of the chosen Company only, so no Company
	condition is needed here."""
	totals = frappe._dict()
	for warehouse, total in paddy_stock_query().run(as_list=True) or []:
		totals[warehouse] = flt(totals.get(warehouse, 0) + flt(total), 3)  # the query groups; adding keeps it right regardless
	return totals


def paddy_stock_columns(columns: list[dict]) -> list[dict]:
	"""The same columns with the stock_balance column called Paddy Stock (QT, three decimals)."""
	for column in columns:
		if column.get("fieldname") == "stock_balance":
			column["label"] = _(LABEL)
			column["precision"] = 3
	return columns


def install(*args, **kwargs):
	"""Replace the two functions of ERPNext's report module. Safe to call any number of times."""
	import importlib

	module = importlib.import_module(REPORT_MODULE)
	if getattr(module, _MARK, None):
		return
	original_balance, original_columns = module.get_warehouse_wise_balance, module.get_columns

	def get_columns(filters):
		return paddy_stock_columns(original_columns(filters))

	module._ivri_od_original = (original_balance, original_columns)
	module.get_warehouse_wise_balance = get_paddy_stock_by_warehouse
	module.get_columns = get_columns
	setattr(module, _MARK, True)


def uninstall():
	"""Put ERPNext's own functions back (used by tests, and to switch this off)."""
	import importlib

	module = importlib.import_module(REPORT_MODULE)
	if not getattr(module, _MARK, None):
		return
	module.get_warehouse_wise_balance, module.get_columns = module._ivri_od_original
	delattr(module, "_ivri_od_original")
	delattr(module, _MARK)
