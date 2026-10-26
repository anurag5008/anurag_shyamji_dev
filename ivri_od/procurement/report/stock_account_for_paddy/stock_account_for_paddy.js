// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Stock Account for Paddy"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "kms_season",
			label: __("KMS Season"),
			fieldtype: "Link",
			options: "Season Master",
			reqd: 1,
		},
		{
			fieldname: "paddy_account",
			label: __("Paddy Account"),
			fieldtype: "Link",
			options: "District Master",
			reqd: 1,
		},
		{
			fieldname: "item_code",
			label: __("Paddy Item"),
			fieldtype: "Link",
			options: "Item",
			description: __("Select a Paddy Item or a Paddy Item Group"),
			get_query: () => {
				const item_group = frappe.query_report.get_filter_value("item_group");
				return { filters: Object.assign({ is_stock_item: 1 }, item_group ? { item_group } : {}) };
			},
		},
		{
			fieldname: "item_group",
			label: __("Paddy Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "from_month",
			label: __("From Month"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_month",
			label: __("To Month"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
