// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Chhatni Tracking"] = {
	collapsible_filters: true,
	filters: [
		{
			fieldname: "season",
			label: __("Season"),
			fieldtype: "Link",
			options: "Season Master",
		},
		{
			fieldname: "ppc_name",
			label: __("PPC Name"),
			fieldtype: "Link",
			options: "PPC Master",
		},
		{
			fieldname: "mill_name",
			label: __("Mill Name"),
			fieldtype: "Link",
			options: "Mill Master",
		},
		{
			fieldname: "transit_pass_no",
			label: __("Transit Pass No"),
			fieldtype: "Data",
		},
	],
};
