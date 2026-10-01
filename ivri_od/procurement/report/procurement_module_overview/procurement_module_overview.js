// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Procurement Module Overview"] = {
	filters: [],
	onload(report) {
		report.page.hide_form();
	},
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "name" && data.open_link) {
			return `<a href="${data.open_link}">${frappe.utils.escape_html(value)}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
};
