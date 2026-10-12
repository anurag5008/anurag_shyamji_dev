// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Entry Report"] = {
	collapsible_filters: true,
	filters: [
		{
			fieldname: "season",
			label: __("Season"),
			fieldtype: "Link",
			options: "Season Master",
		},
		{
			fieldname: "ppc_name",
			label: __("PPC"),
			fieldtype: "Link",
			options: "PPC Master",
			get_query: () => {
				const season = frappe.query_report.get_filter_value("season");
				const mill_name = frappe.query_report.get_filter_value("mill_name");
				return {
					query: "ivri_od.procurement.report.abstract_report.abstract_report.get_eligible_ppcs_query",
					filters: {
						season: season || "",
						mill_name: mill_name || "",
					},
				};
			},
		},
		{
			fieldname: "mill_name",
			label: __("Mill"),
			fieldtype: "Link",
			options: "Mill Master",
		},
	],
	get_datatable_options(options) {
		return Object.assign(options, {
			layout: "fixed",
			cellHeight: 36,
		});
	},
	formatter(value, row, column, data, default_formatter) {
		const fieldname = (column && (column.fieldname || column.id)) || "";
		if (["tp_qty", "entry_qty"].includes(fieldname)) {
			const num = flt(value);
			return `<div style="text-align: right; font-variant-numeric: tabular-nums; width: 100%;">${num.toFixed(3)}</div>`;
		}
		if (["entry_price", "total_amount"].includes(fieldname)) {
			const num = flt(value);
			return `<div style="text-align: right; font-variant-numeric: tabular-nums; width: 100%;">${num.toFixed(2)}</div>`;
		}
		if (fieldname === "ppc" || fieldname === "ppc_name") {
			if (!value || value === "Total") {
				return default_formatter(value, row, column, data);
			}
			const ppc_id = data ? (data.ppc_code || data.ppc_name || value) : value;
			return `<a class="grey" href="/app/ppc-master/${encodeURIComponent(ppc_id)}" data-doctype="PPC Master" data-name="${encodeURIComponent(ppc_id)}" style="font-weight: 500;">${frappe.utils.escape_html(value)}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
	after_datatable_render(datatable_obj) {
		inject_entry_report_styles();
	},
};

function inject_entry_report_styles() {
	let style = document.getElementById("entry-report-ui-styles");
	if (!style) {
		style = document.createElement("style");
		style.id = "entry-report-ui-styles";
		document.head.appendChild(style);
	}
	style.textContent = `
		.report-wrapper .dt-scrollable {
			overflow-x: auto !important;
		}
		.report-wrapper .dt-header .dt-cell__content {
			font-weight: 600;
			white-space: nowrap;
			text-overflow: ellipsis;
		}
		.report-wrapper .dt-cell__content {
			white-space: nowrap;
			text-overflow: ellipsis;
		}
	`;
}

