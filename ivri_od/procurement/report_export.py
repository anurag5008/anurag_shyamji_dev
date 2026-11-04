# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Export (CSV / Excel) of the ivri_od reports: only the rows the user filtered, with Sl No 1, 2, 3...

Frappe's export already keeps only the rows left by the column filters of the report table
(visible_idx), but it has no serial number. For the reports of this app the file gets a first
column "Sl No" numbered 1..n over the exported rows (total rows stay blank).
Reports of other apps are exported by Frappe as before.

hooks.py: override_whitelisted_methods "frappe.desk.query_report.export_query".
"""

import json

import frappe
from frappe import _
from frappe.desk import query_report
from frappe.desk.reportview import clean_params, parse_json
from frappe.modules.utils import get_module_app
from frappe.utils import cint, sbool

SERIAL_COLUMN = {"label": "Sl No", "fieldname": "sl_no", "fieldtype": "Int", "width": 60}
TOTAL_LABELS = {"total", "grand total"}


def is_app_report(report_name) -> bool:
	module = frappe.get_cached_value("Report", report_name, "module") if report_name else None
	return bool(module) and get_module_app(module) == "ivri_od"


@frappe.whitelist()
def export_query():
	if not is_app_report(frappe.local.form_dict.get("report_name")):
		return query_report.export_query()

	from frappe.desk.utils import pop_csv_params

	form_params = frappe._dict(frappe.local.form_dict)
	csv_params = pop_csv_params(form_params)
	clean_params(form_params)
	parse_json(form_params)
	frappe.permissions.can_export(
		frappe.get_cached_value("Report", form_params.report_name, "ref_doctype"),
		raise_exception=True,
	)

	if cint(form_params.export_in_background):
		user_email = frappe.get_cached_value("User", frappe.session.user, "email")
		frappe.enqueue(
			"ivri_od.procurement.report_export.run_export_query_job",
			user_email=user_email,
			form_params=form_params,
			csv_params=csv_params,
			queue="long",
			now=frappe.flags.in_test,
		)
		frappe.msgprint(
			_(
				"Your report is being generated in the background. You will receive an email on {0} with a download link once it is ready."
			).format(user_email)
		)
		return

	return _export_query(form_params, csv_params)


def run_export_query_job(user_email: str, form_params, csv_params):
	from frappe.desk.utils import send_report_email

	report_name, file_extension, content = _export_query(form_params, csv_params, populate_response=False)
	send_report_email(
		user_email, report_name, file_extension, content, attached_to_name=form_params.report_name
	)


def _export_query(form_params, csv_params, populate_response=True):
	"""Frappe's _export_query, with add_serial_numbers after the rows are filtered."""
	from frappe.desk.utils import get_csv_bytes, provide_binary_file
	from frappe.utils.xlsxutils import handle_html, make_xlsx

	report_name = form_params.report_name
	file_format_type = form_params.file_format_type
	visible_idx = form_params.visible_idx or []  # excluding total row idx
	if isinstance(visible_idx, str):
		visible_idx = json.loads(visible_idx)

	data = frappe._dict(
		query_report.run(
			report_name,
			form_params.filters,
			custom_columns=frappe.parse_json(form_params.custom_columns or "[]"),
			are_default_filters=False,
		)
	)
	data.report_name = report_name
	data.filters = form_params.filters
	data.applied_filters = form_params.applied_filters

	if not data.columns:
		frappe.respond_as_web_page(
			_("No data to export"),
			_("You can try changing the filters of your report."),
		)
		return

	has_total_row = cint(data.get("add_total_row"))
	data.result = filter_rows(
		data.result,
		data.columns,
		visible_idx=None if sbool(form_params.get("ignore_visible_idx")) else visible_idx,
		has_total_row=has_total_row,
	)
	add_serial_numbers(data.columns, data.result, has_total_row)

	query_report.format_fields(data, file_format_type)
	xlsx_data, column_widths, styles = query_report.build_xlsx_data(
		data,
		include_indentation=form_params.include_indentation,
		include_filters=form_params.include_filters,
		include_hidden_columns=form_params.include_hidden_columns,
		build_styles=file_format_type == "Excel",
	)

	if file_format_type == "CSV":
		file_extension = "csv"
		content = get_csv_bytes(
			[[handle_html(v) if isinstance(v, str) else v for v in r] for r in xlsx_data],
			csv_params,
		)
	elif file_format_type == "Excel":
		file_extension = "xlsx"
		content = make_xlsx(xlsx_data, report_name, column_widths=column_widths, styles=styles).getvalue()
	else:
		frappe.throw(
			title=_("Unsupported file format: {0}").format(file_format_type),
			msg=_("Only CSV and Excel formats are supported for export"),
		)

	if form_params.include_filters:
		for value in (data.filters or {}).values():
			suffix = ""
			if isinstance(value, list):
				suffix = "_" + ",".join(value)
			elif isinstance(value, str) and value not in {"Yes", "No"}:
				suffix = f"_{value}"
			if query_report.valid_report_name(report_name, suffix):
				report_name += suffix

	if not populate_response:
		return report_name, file_extension, content

	provide_binary_file(_(report_name), file_extension, content)


def filter_rows(result, columns, visible_idx=None, has_total_row=False):
	"""Only the rows at visible_idx (the rows left by the report table's filters); the total row is made again."""
	if not visible_idx or len(visible_idx) >= len(result) - (1 if has_total_row else 0):
		return result
	visible_idx = set(visible_idx)
	rows = [row for idx, row in enumerate(result) if idx in visible_idx]
	return query_report.add_total_row(rows, columns) if has_total_row else rows


def is_total_row(row) -> bool:
	"""A row of the report's own totals: "Total" / "TOTAL" / "Grand Total" in its first cells."""
	cells = list(row.values() if isinstance(row, dict) else row)[:3]
	return any(isinstance(cell, str) and cell.strip().lower() in TOTAL_LABELS for cell in cells)


def add_serial_numbers(columns, result, has_total_row=False):
	"""First column "Sl No": 1, 2, 3... over the rows; blank on total rows."""
	columns.insert(0, dict(SERIAL_COLUMN))
	last, serial = len(result) - 1, 0
	for idx, row in enumerate(result):
		if (has_total_row and idx == last) or is_total_row(row):
			number = ""
		else:
			serial += 1
			number = serial
		if isinstance(row, dict):
			row[SERIAL_COLUMN["fieldname"]] = number
		else:
			result[idx] = [number, *row]
