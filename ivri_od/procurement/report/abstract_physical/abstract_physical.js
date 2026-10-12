// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Abstract Physical"] = {
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
				return {
					query: "ivri_od.procurement.report.abstract_report.abstract_report.get_eligible_ppcs_query",
					filters: {
						season: season || "",
					},
				};
			},
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const fieldname = (column && (column.fieldname || column.id)) || "";
		if (
			[
				"tp_quantity",
				"physical_paddy",
				"entry_qty",
				"chhatni_quantity",
			].includes(fieldname)
		) {
			const num = flt(value);
			return `<div style="text-align: right; font-variant-numeric: tabular-nums;">${num.toFixed(3)}</div>`;
		}
		if (fieldname === "chhatni_pct") {
			const num = flt(value);
			return `<div style="text-align: right; font-variant-numeric: tabular-nums;">${num.toFixed(2)}%</div>`;
		}
		if (fieldname === "ppc" || fieldname === "ppc_name" || fieldname === "ppc_display") {
			const ppc_id = data ? (data.ppc_name || value) : value;
			return `<a class="grey" href="/app/ppc-master/${encodeURIComponent(ppc_id)}" data-doctype="PPC Master" data-name="${encodeURIComponent(ppc_id)}">${frappe.utils.escape_html(value)}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
};
