// Copyright (c) 2026, Profezzo and contributors

// Filters, links and "Portal View" are shared: public/js/portal_detail_table.bundle.js.
// The saved DC document is linked as "Download_DC" on its RRC or FCI cell (in place of View_RRC / View_FCI).
// details: "Show Detail Rows (Lots)" lists the number of lots read from the DC page (grdDepotFCIbody / grdDepotRRCbody, td[4]).
// edit_district: the District (read from the DC PDF) can be set by hand; it is kept on later reads.
// Top filters as Stock Account for Paddy: Mill Name, KMS Year, District, From Month - To Month
// (on the DC's Generated Date); they replace the shared Mill No. and Seen From / Seen To.
// All empty when the report opens: every DC is shown until a filter is set.
const view_dc_settings = ivri_od.portal.section_report_settings({
	file_link_text: "Download_DC",
	details: true,
	edit_district: true,
});

// KMS Years of the mill's View DC rows (all mills when none is picked), newest first; "" = all years.
function load_view_dc_kms_years(report) {
	return frappe
		.call("ivri_od.procurement.report.view_dc_from_dcro.view_dc_from_dcro.get_kms_years", {
			mill: report.get_filter_value("mill_id") || null,
		})
		.then((r) => {
			const years = ["", ...(r.message || [])];
			const filter = report.get_filter("kms_year");
			filter.df.options = years;
			filter.refresh();
			if (!years.includes(filter.get_value() || "")) {
				return filter.set_value("");
			}
		});
}

view_dc_settings.filters = [
	{
		fieldname: "mill_id",
		label: __("Mill Name"),
		fieldtype: "Link",
		options: "Mill Master",
		on_change: async (report) => {
			await load_view_dc_kms_years(report);
			report.refresh();
		},
	},
	{
		fieldname: "kms_year",
		label: __("KMS Year"),
		fieldtype: "Select",
		description: __("Empty: all years. Only years with View DC rows of the mill"),
	},
	{
		fieldname: "district",
		label: __("District"),
		fieldtype: "Link",
		options: "District Master",
		description: __("Empty: all districts"),
	},
	{
		fieldname: "from_month",
		label: __("From Month"),
		fieldtype: "Date",
		description: __("On the Generated Date of the DC. Empty: all dates"),
	},
	{
		fieldname: "to_month",
		label: __("To Month"),
		fieldtype: "Date",
	},
	...view_dc_settings.filters.filter((f) => !["from_date", "to_date", "mill_id"].includes(f.fieldname)),
];

const view_dc_onload = view_dc_settings.onload;
view_dc_settings.onload = function (report) {
	view_dc_onload && view_dc_onload.call(this, report);
	return load_view_dc_kms_years(report);
};

frappe.query_reports["View DC from DCRO"] = view_dc_settings;
