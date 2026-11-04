// Copyright (c) 2026, Profezzo and contributors

// Same filters as Stock Account for Paddy. With a mill picked, only the KMS Years in which
// it has Transit Passes (none: the list is empty, no statement).
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

// PP bags are typed in the report: press Edit on top (public/js/report_edit.js), then click a PP cell of a
// month (Receipts, Other or an Issue District).
// Saved in Gunny PP Entry; an empty value removes it.
const NBT_SET_PP = "ivri_od.procurement.report.new_nbt_gunny_account.new_nbt_gunny_account.set_pp_bags";
const NBT_PP_ACCOUNTS = { receipts_pp: "Receipts", other_pp: "Other" };

frappe.provide("ivri_od.nbt_gunny");
ivri_od.nbt_gunny.edit_pp = function (month_date, fieldname) {
	const report = frappe.query_report;
	const row = (report.data || []).find((d) => d.month_date === month_date) || {};
	const district = (row.pp_districts || {})[fieldname] || "";
	const account = NBT_PP_ACCOUNTS[fieldname] || "Issue";
	const title = account === "Issue" ? __("Issue {0}", [district]) : __(account);
	const dialog = new frappe.ui.Dialog({
		title: __("PP Bags: {0}, {1}", [title, row.month]),
		fields: [
			{
				fieldname: "bags",
				label: __("PP Bags"),
				fieldtype: "Int",
				default: row[fieldname] || "",
				description: __("Empty or 0 removes the entry."),
			},
		],
		primary_action_label: __("Save"),
		primary_action: ({ bags }) => {
			frappe
				.xcall(NBT_SET_PP, {
					mill: report.get_filter_value("mill"),
					kms_year: report.get_filter_value("kms_year"),
					month: month_date,
					account,
					district,
					bags: bags || 0,
				})
				.then(() => {
					dialog.hide();
					frappe.show_alert({ message: __("PP bags saved"), indicator: "green" });
					report.refresh();
				});
		},
	});
	dialog.show();
};

function nbt_pp_editable(fieldname, data) {
	return (
		data &&
		data.month_date &&
		(NBT_PP_ACCOUNTS[fieldname] || (data.pp_districts || {})[fieldname] !== undefined)
	);
}

frappe.query_reports["New NBT Gunny Account"] = {
	filters: [
		{
			fieldname: "mill",
			label: __("Mill Name"),
			fieldtype: "Link",
			options: "Mill Master",
			reqd: 1,
			on_change: async (report) => {
				await load_gunny_kms_years(report);
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
		// Print, Download > PDF (same statement layout, new_nbt_gunny_account.html, A4 landscape) and Download > Excel.
		ivri_od.report_print.add_buttons(report);
		ivri_od.report_edit.add_button(report, [__("PP bags of Receipts, Other and each Issue District")]);

		return load_gunny_kms_years(report);
	},
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (nbt_pp_editable(column.fieldname, data)) {
			value = ivri_od.report_edit.cell(
				value,
				`ivri_od.nbt_gunny.edit_pp('${data.month_date}', '${column.fieldname}')`,
				Boolean(data[column.fieldname])
			);
		}

		return data && data.bold ? `<b>${value}</b>` : value;
	},
};
