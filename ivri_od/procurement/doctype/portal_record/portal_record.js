// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Portal Record", {
	refresh(frm) {
		render_portal_row(frm);
		render_portal_details(frm);
	},
});

function render_portal_row(frm) {
	let cells = {};
	try {
		cells = JSON.parse(frm.doc.row_data || "{}");
	} catch (e) {
		cells = {};
	}

	const rows = Object.entries(cells)
		.map(
			([header, value]) => `
			<tr>
				<th style="width: 35%">${frappe.utils.escape_html(header)}</th>
				<td>${frappe.utils.escape_html(value)}</td>
			</tr>`
		)
		.join("");

	frm.get_field("row_html").$wrapper.html(
		rows
			? `<table class="table table-bordered table-sm">${rows}</table>`
			: `<p class="text-muted">${__("No data")}</p>`
	);
}

// Detail rows (e.g. the lots of a DC) as on the portal (public/js/portal_detail_table.bundle.js).
function render_portal_details(frm) {
	const parse = (text, fallback) => {
		try {
			return JSON.parse(text || fallback);
		} catch (e) {
			return JSON.parse(fallback);
		}
	};
	const rows = (frm.doc.details || []).map((d) => parse(d.detail_data, "{}"));
	const footer = parse(frm.doc.details_footer, "[]");
	frm.get_field("details_html").$wrapper.html(ivri_od.portal.detail_table_html(rows, footer));
}
