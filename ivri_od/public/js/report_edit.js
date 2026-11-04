// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// Edit / Done button of the reports with values typed in the report (Gunny Stock Report Yearly,
// New NBT Gunny Account, DC Transit Challan from DCRO, View DC from DCRO).
// - Not editing (when the report opens): the cells only show their values; typed ones in blue.
// - Edit: the cells that can be typed are highlighted with a ✎ and open their dialog on a click;
//   a message names what can be edited. Done goes back.
// ivri_od.report_edit.add_button(report, labels) in onload; in the formatter:
// ivri_od.report_edit.is_editing() and ivri_od.report_edit.cell(html, onclick, typed).
frappe.provide("ivri_od.report_edit");

(function () {
	const editing = {}; // report name -> true while editing

	ivri_od.report_edit.is_editing = function () {
		return Boolean(editing[frappe.query_report?.report_name]);
	};

	// labels: what can be edited, e.g. ["Tr. Receipt", "Tr. Issue"]; shown when Edit is pressed.
	ivri_od.report_edit.add_button = function (report, labels = []) {
		editing[report.report_name] = false;
		const button = report.page.add_inner_button(__("Edit"), () => {
			const on = !editing[report.report_name];
			editing[report.report_name] = on;
			button.text(on ? __("Done") : __("Edit"));
			button.toggleClass("btn-primary", on).toggleClass("btn-default", !on);
			if (on) {
				frappe.show_alert({
					message: __("Click a highlighted cell to edit it: {0}", [labels.map((label) => __(label)).join(", ")]),
					indicator: "blue",
				});
			}
			report.render_datatable();
		});
		return button;
	};

	// One cell: while editing, highlighted with a ✎ and opening the dialog (onclick: JS code);
	// else the value, in blue when typed. html: the cell as the formatter made it.
	ivri_od.report_edit.cell = function (html, onclick, typed = false) {
		const typed_style = typed ? "color: var(--blue-600); font-weight: 600;" : "";
		if (!ivri_od.report_edit.is_editing()) {
			return typed ? `<div style="${typed_style}" title="${__("Typed in the report")}">${html}</div>` : html;
		}
		// ✎ and the value on one line (Frappe puts numbers in their own block).
		return `<div style="${typed_style} display: flex; align-items: center; gap: 4px; cursor: pointer;
				background: var(--yellow-highlight-color, #fff7d6); margin: -4px -8px; padding: 4px 8px;"
				title="${__("Click to edit")}" onclick="${onclick}; return false;">
				<span>✎</span><div style="flex: 1; min-width: 0;">${html}</div>
			</div>`;
	};
})();
