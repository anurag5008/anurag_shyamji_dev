// Copyright (c) 2026, Profezzo and contributors

// Filters shared with Paddy Stock Register: public/js/stock_register_filters.js
frappe.query_reports["Rice Stock Register"] = {
	// District is optional here: blank = all districts (as Paddy Stock Register).
	filters: ivri_od.stock_register.filters({ district_optional: true }),
	onload(report) {
		return ivri_od.stock_register.onload(report);
	},
	formatter(value, row, column, data, default_formatter) {
		// Every number shows 0.0000 (not blank), as in the paper register.
		return ivri_od.stock_register.mark_mismatch(default_formatter(value, row, column, data), data);
	},
};
