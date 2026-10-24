// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// List view settings must live in this *_list.js file: Frappe loads the form script only after a form
// of this DocType has been opened, so settings kept there are missing after a page refresh.

// Pass Unique Key is {miller}-{PPC NAME(CODE)}-{K|R}{YY}-TP{no}; the PPC part is the last-resort party name.
function ppcFromPassKey(key) {
	const match = /^[^-]+-(.+?)-[A-Z]\d{2}-TP/i.exec(key || "");
	return match ? match[1] : "";
}

frappe.listview_settings["Weigh Bridge Measurement"] = {
	// The ID column (WBM-2026-00071) is not useful: RST No is the clickable first column.
	hide_name_column: true,
	// Party Name is only stored for Rice Dispatch and Local Paddy Purchase. Transit Pass (Government
	// Paddy Purchase) records show their PPC Name there, else the PPC from the Pass Unique Key.
	// Display only: nothing is saved.
	add_fields: ["pacs_name", "pass_unique_key"],
	formatters: {
		party_name(value, df, doc) {
			const party = frappe.utils.escape_html(
				value || doc.pacs_name || ppcFromPassKey(doc.pass_unique_key)
			);
			return `<span class="ellipsis" title="${__("Party Name")}: ${party}">${party}</span>`;
		},
	},
	onload(listview) {
		listview.page.add_inner_button(__("TP Not Received"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Weigh Bridge Measurement", "tp_status", "=", "TP Not Received"],
			]);
		});
		listview.page.add_inner_button(__("PPC Mismatch"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Weigh Bridge Measurement", "tp_status", "=", "PPC Mismatch"],
			]);
		});
		listview.page.add_inner_button(__("TP Received"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Weigh Bridge Measurement", "tp_status", "=", "TP Received"],
			]);
		});
		listview.page.add_inner_button(__("Rice Dispatch"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Weigh Bridge Measurement", "tp_status", "=", "Rice Dispatch"],
			]);
		});
	},
};
