frappe.query_reports["Abstract Physical"] = {
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
	],
};
