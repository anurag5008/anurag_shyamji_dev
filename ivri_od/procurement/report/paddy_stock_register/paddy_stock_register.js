// Copyright (c) 2026, Profezzo and contributors

// Filters shared with Rice Stock Register: public/js/stock_register_filters.js
const PADDY_BLANK_WHEN_EMPTY = ["release_order", "issue_for_milling"];

frappe.query_reports["Paddy Stock Register"] = {
	// District is optional here: blank = all districts.
	filters: ivri_od.stock_register.filters({ district_optional: true }),
	onload(report) {
		return ivri_od.stock_register.onload(report);
	},
	formatter(value, row, column, data, default_formatter) {
		// Release Order / Issue for Milling: blank cell (not 0.00) when there is no entry that day.
		if (data && PADDY_BLANK_WHEN_EMPTY.includes(column.fieldname) && data[column.fieldname] == null) {
			value = "";
		} else {
			value = default_formatter(value, row, column, data);
		}
		return ivri_od.stock_register.mark_mismatch(value, data);
	},
};
