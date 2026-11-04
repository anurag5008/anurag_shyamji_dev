// Copyright (c) 2026, Profezzo and contributors

// KMS Years from Season Master, newest first ("24-25" = 01-11-2024 to 31-10-2025).
function load_custody_kms_years(report) {
	return frappe
		.call("ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy.get_kms_years")
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

frappe.query_reports["Joint Custody and Maintenance Charge Report"] = {
	filters: [
		{
			fieldname: "mill",
			label: __("Mill No"),
			fieldtype: "Link",
			options: "Mill Master",
			reqd: 1,
			on_change: (report) => {
				// The mill's District and name (printed in the heading) come from Mill Master.
				const mill = report.get_filter_value("mill");
				if (!mill) {
					report.set_filter_value("miller_name", "");
					return;
				}
				frappe.db.get_value("Mill Master", mill, ["company", "district"]).then((r) => {
					const values = r.message || {};
					report.set_filter_value({
						miller_name: values.company || mill,
						district: values.district || report.get_filter_value("district") || "",
					});
				});
			},
		},
		{
			fieldname: "kms_year",
			label: __("KMS Year"),
			fieldtype: "Select",
			reqd: 1,
			description: __("1 Nov to 31 Oct, e.g. 24-25 = 01-11-2024 to 31-10-2025"),
		},
		{
			fieldname: "district",
			label: __("District"),
			fieldtype: "Link",
			options: "District Master",
			reqd: 1,
		},
		{
			// Calendar of months only (any year), as in Stock Account for Paddy and Rice Stock Report.
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
			fieldname: "miller_name",
			label: __("Miller Name"),
			fieldtype: "Data",
			hidden: 1,
		},
	],
	onload(report) {
		// Print, Download > PDF (joint_custody_and_maintenance_charge_report.html, A4 landscape) and Excel.
		ivri_od.report_print.add_buttons(report);
		return load_custody_kms_years(report);
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
