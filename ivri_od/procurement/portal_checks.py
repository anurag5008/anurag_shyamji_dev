# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Checks that the scraped detail rows of a section match the portal.

DC Monitoring (SCMS): each DC row shows "No. Of Lot" and "Receipt Qty(In Qtl.)";
its View table (gdvGetPassRegister) lists the lots and ends with a "Total" line.
The saved lots must match both numbers and the portal's Total line, and no lot
may hold header text, "Column N" overflow cells or the Total line itself.

Run from the bench folder:
	bench --site <site> execute ivri_od.procurement.portal_checks.clear_records
	bench --site <site> execute ivri_od.procurement.portal_checks.clear_records --kwargs "{'confirm': 1}"
	bench --site <site> execute ivri_od.procurement.portal_checks.verify_detail_rows
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt

DC_CHECK = {
	"site": "SCMS",
	"section": "DC Monitoring",
	"count_column": "No. Of Lot",
	"qty_column": "Receipt Qty(In Qtl.)",
	"detail_qty_column": "Quantity (In Qtl.)",
}
QTY_TOLERANCE = 0.01
OVERFLOW_HEADER = re.compile(r"^Column \d+$")
TOTAL_VALUE = re.compile(r"^(grand |sub ?)?total\s*:?$", re.IGNORECASE)


def clear_records(site: str = DC_CHECK["site"], section: str = DC_CHECK["section"], confirm: int = 0) -> int:
	"""Delete the Portal Records of one section so the next extraction starts clean.
	Without ``confirm=1`` it only reports how many would be deleted."""
	frappe.only_for("System Manager")
	names = frappe.get_all("Portal Record", filters={"site": site, "section": section}, pluck="name")
	if not cint(confirm):
		print(f"Dry run: {len(names)} Portal Record(s) of {site} / {section} would be deleted. Pass confirm=1.")
		return len(names)
	for name in names:
		frappe.delete_doc("Portal Record", name, ignore_permissions=True)
	frappe.db.commit()
	print(f"Deleted {len(names)} Portal Record(s) of {site} / {section}.")
	return len(names)


def verify_detail_rows(
	site: str = DC_CHECK["site"],
	section: str = DC_CHECK["section"],
	count_column: str = DC_CHECK["count_column"],
	qty_column: str = DC_CHECK["qty_column"],
	detail_qty_column: str = DC_CHECK["detail_qty_column"],
	quiet: int = 0,
) -> dict:
	"""Compare each record's detail rows with the counts shown on the portal row."""
	records = frappe.get_all(
		"Portal Record",
		filters={"site": site, "section": section},
		fields=["name", "summary", "row_data", "details_footer"],
		order_by="summary",
	)
	result = {"records": len(records), "passed": 0, "failed": 0, "problems": []}
	for record in records:
		problems = check_record(record, count_column, qty_column, detail_qty_column)
		if problems:
			result["failed"] += 1
			result["problems"].append({"record": record.name, "summary": record.summary, "problems": problems})
		else:
			result["passed"] += 1

	if not cint(quiet):
		for item in result["problems"]:
			print(f"FAIL {item['summary']} ({item['record']}): " + "; ".join(item["problems"]))
		print(
			f"{site} / {section}: {result['records']} record(s), "
			f"{result['passed']} match the portal, {result['failed']} do not."
		)
	return result


def check_record(record, count_column: str, qty_column: str, detail_qty_column: str) -> list[str]:
	row = json.loads(record.row_data or "{}")
	details = [
		json.loads(d or "{}")
		for d in frappe.get_all(
			"Portal Record Detail", filters={"parent": record.name}, pluck="detail_data", order_by="idx"
		)
	]

	problems = []
	if count_column in row and cint(row[count_column]) != len(details):
		problems.append(_("lots: portal {0}, ERP {1}").format(row[count_column], len(details)))
	if qty_column in row:
		erp_qty = sum(flt(d.get(detail_qty_column)) for d in details)
		if abs(flt(row[qty_column]) - erp_qty) > QTY_TOLERANCE:
			problems.append(_("qty: portal {0}, ERP {1}").format(flt(row[qty_column]), round(erp_qty, 3)))

	footer = json.loads(record.details_footer or "[]")
	for total in footer:
		if detail_qty_column in total:
			erp_qty = sum(flt(d.get(detail_qty_column)) for d in details)
			if abs(flt(total[detail_qty_column]) - erp_qty) > QTY_TOLERANCE:
				problems.append(
					_("lot table Total {0}, sum of lots {1}").format(flt(total[detail_qty_column]), round(erp_qty, 3))
				)

	for line, detail in enumerate(details, start=1):
		if any(OVERFLOW_HEADER.match(h) and v for h, v in detail.items()):
			problems.append(_("line {0}: values in 'Column N' (columns shifted)").format(line))
		if sum(1 for h, v in detail.items() if v and v == h) > 1:
			problems.append(_("line {0}: holds header text").format(line))
		if any(TOTAL_VALUE.match(v or "") for v in detail.values()):
			problems.append(_("line {0}: is the 'Total' footer").format(line))
	return problems
