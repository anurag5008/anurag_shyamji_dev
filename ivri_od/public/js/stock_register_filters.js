// Copyright (c) 2026, Profezzo and contributors

// Shared filters of the day-wise stock registers (Paddy Stock Register, Rice Stock Register):
// Mill Name -> KMS Year ("25-26") -> Season (Kharif / Rabi) -> District -> From / To Date (+ hidden Company).
// Use: filters: ivri_od.stock_register.filters(), onload(report) { return ivri_od.stock_register.onload(report); }
frappe.provide("ivri_od.stock_register");

(function () {
	// KMS Years from Season Master, newest first; with a mill picked, only the years it has Transit Passes.
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

	// options.district_optional: District not mandatory and not filled from the mill;
	// blank District = all districts (Paddy Stock Register).
	ivri_od.stock_register.filters = function (options = {}) {
		const district_optional = !!options.district_optional;
		return [
			{
				fieldname: "mill",
				label: __("Mill Name"),
				fieldtype: "Link",
				options: "Mill Master",
				reqd: 1,
				on_change: async (report) => {
					await load_kms_years(report);
					// The mill's company is printed in headings; its District is the default District.
					const mill = report.get_filter_value("mill");
					const { company = "", district = "" } = mill
						? (await frappe.db.get_value("Mill Master", mill, ["company", "district"])).message || {}
						: {};
					if (!district_optional && district && !report.get_filter_value("district")) {
						await report.set_filter_value("district", district);
					}
					// Setting the same company again does not refresh the report, so refresh here.
					if (company === (report.get_filter_value("company") || "")) {
						report.refresh();
					} else {
						report.set_filter_value("company", company);
					}
				},
			},
			{
				fieldname: "kms_year",
				label: __("KMS Year"),
				fieldtype: "Select",
				reqd: 1,
			},
			{
				fieldname: "season",
				label: __("Season"),
				fieldtype: "Select",
				options: "Kharif\nRabi",
				default: "Kharif",
				reqd: 1,
				description: __("Prog. columns count from the season's Start Date in Season Master, if set"),
			},
			{
				fieldname: "district",
				label: __("District"),
				fieldtype: "Link",
				options: "District Master",
				reqd: district_optional ? 0 : 1,
				get_query: () => ({ filters: { is_active: 1 } }),
				description: district_optional
					? __("District account (AC) printed in the heading; blank = all districts")
					: __("District account (AC) printed in the heading; default: the mill's District"),
			},
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				reqd: 1,
				default: frappe.datetime.month_start(),
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Link",
				options: "Company",
				hidden: 1,
			},
		];
	};

	ivri_od.stock_register.onload = function (report) {
		// Print, Download > PDF (the report's .html, A4 landscape) and Download > Excel.
		ivri_od.report_print.add_buttons(report);
		return load_kms_years(report);
	};

	// Red row when C.B. does not match the check (data.mismatch from the server).
	ivri_od.stock_register.mark_mismatch = function (value, data) {
		return data && data.mismatch ? `<span style="color: var(--red-600)">${value}</span>` : value;
	};
})();
