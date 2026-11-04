// Copyright (c) 2026, Profezzo and contributors

// KMS Years from Season Master, newest first ("25-26" = Kharif 2025 and Rabi 2025); with a mill
// picked, only the years in which it has Transit Passes (none: the list is empty, no statement).
function load_kms_years(report) {
	return frappe
		.call("ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy.get_kms_years", {
			mill: report.get_filter_value("mill") || null,
		})
		.then((r) => {
			const years = r.message || [];
			const filter = report.get_filter("kms_year");
			filter.df.options = years;
			filter.refresh();
			if (!years.includes(filter.get_value())) {
				return filter.set_value(years[0] || "");
			}
		});
}

frappe.query_reports["Stock Account for Paddy"] = {
	filters: [
		{
			fieldname: "mill",
			label: __("Mill Name"),
			fieldtype: "Link",
			options: "Mill Master",
			reqd: 1,
			on_change: async (report) => {
				// Only the KMS Years with Transit Passes of this mill.
				await load_kms_years(report);
				// The mill's company is printed in the heading.
				const mill = report.get_filter_value("mill");
				const company_of_mill = mill
					? frappe.db.get_value("Mill Master", mill, "company").then((r) => r.message?.company || "")
					: Promise.resolve("");
				company_of_mill.then((company) => {
					// Setting the same company again does not refresh the report, so refresh here.
					if (company === (report.get_filter_value("company") || "")) {
						report.refresh();
					} else {
						report.set_filter_value("company", company);
					}
				});
			},
		},
		{
			fieldname: "kms_year",
			label: __("KMS Year"),
			fieldtype: "Select",
			reqd: 1,
			description: __("Kharif and Rabi of the year; only years with Transit Passes of the mill"),
		},
		{
			fieldname: "paddy_account",
			label: __("District"),
			fieldtype: "Link",
			options: "District Master",
			reqd: 1,
			description: __("PPCs assigned to this district in PPC Master"),
		},
		{
			// Calendar of months only (any year): picking a month gives its 1st day; the report
			// takes the whole month.
			fieldname: "from_month",
			label: __("From Month"),
			fieldtype: "Date",
			options: { view: "months", minView: "months" },
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_month",
			label: __("To Month"),
			fieldtype: "Date",
			options: { view: "months", minView: "months" },
			reqd: 1,
			default: frappe.datetime.month_end(),
			// The calendar gives the 1st of the month: show its last day, so the user sees the
			// whole month is counted (e.g. 31-01-2027).
			on_change: (report) => {
				const value = report.get_filter_value("to_month");
				const month_end = value && moment(value).endOf("month").format("YYYY-MM-DD");
				if (month_end && value !== month_end) {
					report.set_filter_value("to_month", month_end); // runs this again, then refreshes
				} else {
					report.refresh();
				}
			},
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			hidden: 1,
		},
	],
	onload(report) {
		// Print, Download > PDF (same statement layout, stock_account_for_paddy.html, A4 landscape) and Download > Excel.
		ivri_od.report_print.add_buttons(report);

		return load_kms_years(report);
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
