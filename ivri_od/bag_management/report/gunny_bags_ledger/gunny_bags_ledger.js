// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Gunny Bags Ledger"] = {
	filters: [
		{
			// the mills come from Mill Master; the list is read when the dropdown opens, nothing is typed in here
			fieldname: "mill",
			label: __("Mill Name"),
			fieldtype: "Link",
			options: "Mill Master",
			reqd: 1,
		},
	],
	onload(report) {
		// Report filters are one narrow column wide, which cuts a long mill name.
		// Give this filter the room to show the full name.
		const filter = report.get_filter("mill");
		if (filter) {
			$(filter.wrapper).removeClass("col-md-2").css({ flex: "0 0 auto", width: "440px", maxWidth: "100%" });
		}
	},
};
