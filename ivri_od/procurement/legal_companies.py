# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""The legal Companies.

A legal Company is one that operating units account to: the `accounting_company` of a Mill Master. (The `company` of a
Mill Master is the older operating-unit Company, e.g. the Raw / Boiled variants; those are not legal Companies.)
The three approved legal Companies in inventory_foundation.LEGAL_COMPANIES are always included. No Company is
recognised by its name, so a new legal Company only needs its operating units mapped to it.

Used to limit the Company dropdown of ERPNext's Warehouse Wise Stock Balance report (public/js/warehouse_wise_stock_balance.js).
Reads only.
"""

import frappe

from ivri_od.procurement.inventory_foundation import LEGAL_COMPANIES


def legal_company_names() -> list[str]:
	"""Approved legal Companies plus every accounting_company set on a Mill Master, sorted."""
	mapped = frappe.get_all(
		"Mill Master", filters={"accounting_company": ["is", "set"]}, pluck="accounting_company", distinct=True
	)
	return sorted({*LEGAL_COMPANIES.values(), *(name for name in mapped if (name or "").strip())})


@frappe.whitelist()
def get_legal_companies() -> list[str]:
	"""The legal Companies that exist and that the user may read."""
	return frappe.get_list("Company", filters={"name": ["in", legal_company_names()]}, pluck="name", order_by="name")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def legal_company_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field search for Company, limited to the legal Companies."""
	rows = frappe.get_list(
		"Company",
		filters=[["name", "in", legal_company_names()], ["name", "like", f"%{txt or ''}%"]],
		pluck="name",
		order_by="name",
		limit_start=start,
		limit_page_length=page_len,
	)
	return [[name] for name in rows]
