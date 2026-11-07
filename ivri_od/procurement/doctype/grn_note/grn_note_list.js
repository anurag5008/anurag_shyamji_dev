// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// List view settings must live in this *_list.js file: Frappe loads the form script only after a form
// of this DocType has been opened, so settings kept there are missing after a page refresh.

// Mill Name holds "SHREE SHYAMJI PADDY PROCESSING PVT LTD(M051007)". The list shows the mill's Short Name
// from Mill Master (SSPPB), which is much shorter. Display only: nothing is saved.
const GRN_MILL_SHORT_NAMES = {};

function load_grn_mill_short_names() {
	return frappe.db.get_list("Mill Master", { fields: ["name", "short_name"], limit: 100 }).then((rows) => {
		(rows || []).forEach((row) => {
			if (row.short_name) GRN_MILL_SHORT_NAMES[row.name] = row.short_name;
		});
	});
}

frappe.listview_settings["GRN Note"] = {
	// GRN No is the first column; the ID column and the ID filter repeat it.
	hide_name_column: true,
	onload(listview) {
		load_grn_mill_short_names().then(() => listview.refresh());
	},
	formatters: {
		mill_name(value) {
			const text = value || "";
			const code = (/\(([^)]+)\)\s*$/.exec(text) || [])[1] || text;
			const short = GRN_MILL_SHORT_NAMES[code.trim()] || text;
			return `<span class="ellipsis" title="${frappe.utils.escape_html(text)}">${frappe.utils.escape_html(short)}</span>`;
		},
	},
};
