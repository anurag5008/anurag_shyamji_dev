# Copyright (c) 2026, Profezzo and contributors
"""Excel column ↔ PPAS Transit Pass field mapping (single source of truth)."""

import frappe

# Standard Excel export columns (date and time are always separate).
STANDARD_EXCEL_COLUMNS = [
	"Sl#",
	"PACS",
	"PPC",
	"Miller",
	"Transit Pass No.",
	"Vehicle No",
	"Driver Name",
	"Bag",
	"Quantity",
	"Transit Pass Date",
	"Transit Pass Time",
	"Delay(In Days)",
	"Accepted Date",
	"Accepted Time",
	"Action",
]

PPAS_COLUMN_MAPPING = [
	{"excel_column": "Sl#", "fieldname": "sl", "label": "SL", "fieldtype": "Int"},
	{"excel_column": "PACS", "fieldname": "pacs", "label": "PACS", "fieldtype": "Data"},
	{"excel_column": "PPC", "fieldname": "ppc", "label": "PPC", "fieldtype": "Data"},
	{"excel_column": "Miller", "fieldname": "miller", "label": "Miller", "fieldtype": "Data"},
	{
		"excel_column": "Transit Pass No.",
		"fieldname": "transit_pass_no",
		"label": "Transit Pass No",
		"fieldtype": "Data",
	},
	{"excel_column": "Vehicle No", "fieldname": "vehicle_no", "label": "Vehicle No", "fieldtype": "Data"},
	{"excel_column": "Driver Name", "fieldname": "driver_name", "label": "Driver Name", "fieldtype": "Data"},
	{"excel_column": "Bag", "fieldname": "bags", "label": "No of Bag", "fieldtype": "Int"},
	{"excel_column": "Quantity", "fieldname": "quantity", "label": "Quantity", "fieldtype": "Float"},
	{
		"excel_column": "Transit Pass Date",
		"fieldname": "transit_pass_date",
		"label": "Transit Pass Date",
		"fieldtype": "Date",
	},
	{
		"excel_column": "Transit Pass Time",
		"fieldname": "transit_pass_time",
		"label": "Transit Pass Time",
		"fieldtype": "Time",
	},
	{
		"excel_column": "Delay(In Days)",
		"fieldname": "delay_in_days",
		"label": "Delay (In Days)",
		"fieldtype": "Int",
	},
	{
		"excel_column": "Accepted Date",
		"fieldname": "accepted_date",
		"label": "Accepted Date",
		"fieldtype": "Date",
	},
	{
		"excel_column": "Accepted Time",
		"fieldname": "accepted_time",
		"label": "Accepted Time",
		"fieldtype": "Time",
	},
	{"excel_column": "Action", "fieldname": "action", "label": "Action", "fieldtype": "Data"},
]

# DocType-only field filled from extraction (not a separate Excel column).
EXTRA_DOCTYPE_FIELDS = [
	{"fieldname": "season", "label": "Season", "source": "PPAS Data Extraction.season (stored as text)"},
]


@frappe.whitelist()
def get_ppas_column_mapping():
	return {
		"excel_to_doctype": PPAS_COLUMN_MAPPING,
		"extra_doctype_fields": EXTRA_DOCTYPE_FIELDS,
		"standard_excel_columns": STANDARD_EXCEL_COLUMNS,
		"target_doctype": "PPAS Transit Pass",
	}


def get_mapping_html():
	rows = []
	for item in PPAS_COLUMN_MAPPING:
		rows.append(
			f"<tr><td><b>{item['excel_column']}</b></td>"
			f"<td>{item['fieldname']}</td>"
			f"<td>{item['label']}</td>"
			f"<td>{item['fieldtype']}</td></tr>"
		)

	extra_rows = []
	for item in EXTRA_DOCTYPE_FIELDS:
		extra_rows.append(
			f"<tr><td><i>(auto)</i></td>"
			f"<td>{item['fieldname']}</td>"
			f"<td>{item['label']}</td>"
			f"<td>{item['source']}</td></tr>"
		)

	return f"""
	<div class="text-muted" style="margin-bottom:8px;">
		Scraped Excel columns map into <b>PPAS Transit Pass</b>.
		Date and time are stored in separate columns.
	</div>
	<table class="table table-bordered table-sm" style="font-size:12px;">
		<thead>
			<tr>
				<th>Excel column</th>
				<th>DocType field</th>
				<th>Label</th>
				<th>Type / source</th>
			</tr>
		</thead>
		<tbody>
			{''.join(rows)}
			{''.join(extra_rows)}
		</tbody>
	</table>
	"""
