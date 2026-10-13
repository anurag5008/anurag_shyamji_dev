// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Pass RST WBM Summary"] = {
	collapsible_filters: true,
	filters: [
		{
			fieldname: "season",
			label: __("Season"),
			fieldtype: "Link",
			options: "Season Master",
		},
		{
			fieldname: "pass_unique_key",
			label: __("Pass Unique Key"),
			fieldtype: "Link",
			options: "PPAS Transit Pass",
		},
		{
			fieldname: "from_date",
			label: __("WBM From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("WBM To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "tp_completed",
			label: __("TP Completed"),
			fieldtype: "Select",
			options: "\nYes\nNo",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "tp_completed" && !row.indent) {
			const indicator = value === __("Yes") ? "green" : value === __("No") ? "orange" : "grey";
			return `<span class="indicator-pill ${indicator} filterable ellipsis">${__(
				value || ""
			)}</span>`;
		}
		return default_formatter(value, row, column, data);
	},
};
