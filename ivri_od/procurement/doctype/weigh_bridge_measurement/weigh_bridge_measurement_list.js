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
	// No ID filter: RST No, Party Name, TP No, Lot No, Truck No and Commodity are the filters staff use.
	// Each one is a drop-down of the values that exist in the weighments.
	hide_name_filter: true,
	onload(listview) {
		// Open with no filter: Frappe remembers the filters used last time, which hid data from staff.
		// A link with filters in its address (route options) is left alone.
		if (!Object.keys(frappe.route_options || {}).length && listview.filter_area) {
			listview.filter_area.clear();
		}
		const fieldnames = ["rst_no", "party_name", "transit_pass_no", "lot_no", "actual_truck_no", "commodity"];
		frappe
			.xcall("ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.get_filter_values")
			.then((values) => {
				// The filter fields are made a moment after the list opens: wait for them.
				let tries = 0;
				const timer = setInterval(() => {
					tries += 1;
					const ready = fieldnames.filter((name) => listview.page.fields_dict[name]);
					ready.forEach((name) => {
						const field = listview.page.fields_dict[name];
						if (field.set_data && !field.__wbm_values_set) {
							field.__wbm_values_set = true;
							field.set_data(values[name] || []);
						}
					});
					if (ready.length === fieldnames.length || tries > 40) {
						clearInterval(timer);
					}
				}, 250);
			});
	},
};
