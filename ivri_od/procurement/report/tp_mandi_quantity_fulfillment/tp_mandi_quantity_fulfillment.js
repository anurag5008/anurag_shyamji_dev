// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.query_reports["TP Mandi Quantity Fulfillment"] = {
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
