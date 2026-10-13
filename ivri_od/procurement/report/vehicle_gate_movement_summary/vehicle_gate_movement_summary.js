// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Vehicle Gate Movement Summary"] = {
	collapsible_filters: true,
	filters: [
		{ fieldname: "from_date", label: __("Entry From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Entry To Date"), fieldtype: "Date" },
		{ fieldname: "vehicle_no", label: __("Vehicle No"), fieldtype: "Data" },
		{
			fieldname: "mill_status",
			label: __("Mill Status"),
			fieldtype: "Select",
			options: "\nInside Mill\nExited",
			description: __("Inside Mill: Gate In with no Gate Out / Gate Exit yet."),
		},
	],
};
