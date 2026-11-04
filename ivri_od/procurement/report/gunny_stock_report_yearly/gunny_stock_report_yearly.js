// Copyright (c) 2026, Profezzo and contributors

// Filters as Stock Account for Paddy. KMS Years from Season Master, newest first ("25-26" = Kharif
// 2025 and Rabi 2025); with a mill picked, only the years in which it has Transit Passes.
function load_gunny_kms_years(report) {
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

// Typed columns: press Edit on top (public/js/report_edit.js), then click a typed column's cell of a
// month. Saved in Gunny Stock Yearly Entry; an empty value removes it. Not editing, they only show their values (0 when none).
const GUNNY_YEARLY_SET_VALUE = "ivri_od.procurement.report.gunny_stock_report_yearly.gunny_stock_report_yearly.set_value";
const GUNNY_YEARLY_MANUAL = {
	tr_receipt: "Int",
	old_bag_rate: "Currency",
	tr_issue: "Int",
	old_procured: "Int",
	old_used: "Int",
	unused_cost: "Currency",
};
// Labels of the typed columns (as in get_columns of the .py). Fixed here because onload runs before
// the report's columns are loaded: report.columns is empty on a fresh page.
const GUNNY_YEARLY_LABELS = {
	tr_receipt: "Tr. Receipt",
	old_bag_rate: "Actual Cost of Old Bags Procured",
	tr_issue: "Tr. Issue",
	old_procured: "Old Bags - Procured from CKMS",
	old_used: "No. of Old Bags Used in Current KMS",
	unused_cost: "Actual Cost of Unused Bags",
};

frappe.provide("ivri_od.gunny_yearly");
ivri_od.gunny_yearly.edit = function (month_date, fieldname) {
	const report = frappe.query_report;
	const row = (report.data || []).find((d) => d.month_date === month_date) || {};
	const label = GUNNY_YEARLY_LABELS[fieldname] || fieldname;
	// Tr. Receipt: only the typed part is edited; Tr. Issues of other accounts are added by the report.
	const transfer = fieldname === "tr_receipt" ? row.tr_receipt_transfer || 0 : 0;
	const typed = fieldname === "tr_receipt" ? row.tr_receipt_typed : row[fieldname];
	const dialog = new frappe.ui.Dialog({
		title: __("{0}, {1}", [__(label), row.month]),
		fields: [
			{
				fieldname: "value",
				label: __(label),
				fieldtype: GUNNY_YEARLY_MANUAL[fieldname],
				default: typed || "",
				description: transfer
					? __("Typed here only. {0} more come from Tr. Issues of other accounts in the same month. Empty or 0 removes the entry.", [
							format_number(transfer, null, 0),
					  ])
					: __("Empty or 0 removes the entry."),
			},
		],
		primary_action_label: __("Save"),
		primary_action: ({ value }) => {
			frappe
				.xcall(GUNNY_YEARLY_SET_VALUE, {
					mill: report.get_filter_value("mill"),
					kms_year: report.get_filter_value("kms_year"),
					district: report.get_filter_value("paddy_account"),
					month: month_date,
					fieldname,
					value: value || 0,
				})
				.then(() => {
					dialog.hide();
					frappe.show_alert({ message: __("Saved"), indicator: "green" });
					report.refresh();
				});
		},
	});
	dialog.show();
};

frappe.query_reports["Gunny Stock Report Yearly"] = {
	filters: [
		{
			fieldname: "mill",
			label: __("Mill Name"),
			fieldtype: "Link",
			options: "Mill Master",
			reqd: 1,
			on_change: async (report) => {
				await load_gunny_kms_years(report);
				// The mill's company is printed in the heading ("NAME OF THE MILLER").
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
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			hidden: 1,
		},
	],
	onload(report) {
		// Print, Download > PDF (statement layout, gunny_stock_report_yearly.html, A4 landscape), Excel and CSV.
		ivri_od.report_print.add_buttons(report);
		ivri_od.report_edit.add_button(report, Object.values(GUNNY_YEARLY_LABELS));

		return load_gunny_kms_years(report);
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.month_date && GUNNY_YEARLY_MANUAL[column.fieldname]) {
			value = ivri_od.report_edit.cell(
				value,
				`ivri_od.gunny_yearly.edit('${data.month_date}', '${column.fieldname}')`,
				Boolean(column.fieldname === "tr_receipt" ? data.tr_receipt_typed || data.tr_receipt_transfer : data[column.fieldname])
			);
		}

		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
