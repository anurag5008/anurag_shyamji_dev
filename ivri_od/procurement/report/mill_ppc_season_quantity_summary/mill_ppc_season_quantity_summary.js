frappe.query_reports["Mill PPC Season Quantity Summary"] = {
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
			label: __("Mill"),
			fieldtype: "Link",
			options: "Mill Master",
		},
	],
};
