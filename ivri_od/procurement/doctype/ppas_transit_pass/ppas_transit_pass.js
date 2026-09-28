// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

const PPAS_LIST_COLUMN_ORDER = [
	"sl",
	"transit_pass_no",
	"season",
	"ppc",
	"bags",
	"delay_in_days",
	"quantity",
];

const PPAS_EXTRA_LIST_COLUMNS = ["bags", "delay_in_days"];

function ensure_ppas_transit_pass_list_columns(listview) {
	const present = new Set(
		(listview.columns || [])
			.filter((col) => col.type === "Field" && col.df)
			.map((col) => col.df.fieldname)
	);

	let changed = false;
	for (const fieldname of PPAS_EXTRA_LIST_COLUMNS) {
		if (present.has(fieldname)) {
			continue;
		}

		const df = frappe.meta.get_docfield("PPAS Transit Pass", fieldname);
		if (!df) {
			continue;
		}

		listview.columns.push({
			type: "Field",
			df,
		});
		changed = true;
	}

	return changed;
}

function reorder_ppas_transit_pass_list_columns(listview) {
	const columns = listview.columns || [];
	const fixed = columns.filter(
		(col) => col.type === "Subject" || col.type === "Tag" || col.type === "Status"
	);
	const field_columns = columns.filter((col) => col.type === "Field" && col.df);
	const by_fieldname = {};

	field_columns.forEach((col) => {
		by_fieldname[col.df.fieldname] = col;
	});

	const ordered = [...fixed];
	for (const fieldname of PPAS_LIST_COLUMN_ORDER) {
		if (by_fieldname[fieldname]) {
			ordered.push(by_fieldname[fieldname]);
			delete by_fieldname[fieldname];
		}
	}

	Object.values(by_fieldname).forEach((col) => ordered.push(col));
	listview.columns = ordered;
}

frappe.listview_settings["PPAS Transit Pass"] = {
	add_fields: [
		"sl",
		"transit_pass_no",
		"bags",
		"delay_in_days",
		"quantity",
		"pacs",
		"season",
		"ppc",
	],
	onload(listview) {
		const added = ensure_ppas_transit_pass_list_columns(listview);
		reorder_ppas_transit_pass_list_columns(listview);
		if (added) {
			listview.refresh(true);
		}

		if (frappe.user.has_role("System Manager")) {
			listview.page.add_menu_item(__("Delete All Transit Passes"), () => {
				frappe.confirm(
					__(
						"Permanently delete ALL PPAS Transit Pass records? This cannot be undone."
					),
					() => {
						frappe.call({
							method:
								"ivri_od.procurement.doctype.ppas_transit_pass.ppas_transit_pass.delete_all_transit_passes",
							freeze: true,
							freeze_message: __("Deleting..."),
							callback(r) {
								frappe.show_alert({
									message: r.message || __("Deleted"),
									indicator: "green",
								});
								listview.refresh();
							},
						});
					}
				);
			});
		}
	},
};

frappe.ui.form.on("PPAS Transit Pass", {
	refresh(frm) {
		//
	},
});
