// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Stock by Physical Location"] = {
	collapsible_filters: true,
	filters: [
		{ fieldname: "physical_location", label: __("Physical Location"), fieldtype: "Link", options: "Physical Location" },
		{ fieldname: "operating_unit", label: __("Operating Unit (Owner)"), fieldtype: "Link", options: "Mill Master" },
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "item_code", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "season", label: __("Procurement Season"), fieldtype: "Link", options: "Season Master" },
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: "Owner-wise and combined\nOwner-wise only\nCombined physical only",
			default: "Owner-wise and combined",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.is_combined ? `<b>${value}</b>` : value;
	},
};
