// Copyright (c) 2026, Profezzo and contributors

frappe.ui.form.on("PPAS Transit Pass Import", {
	refresh(frm) {
		if (frm.is_new()) {
			frm.clear_table("import_items");
			frm.set_value("total_records", 0);
			frm.set_value("duplicate_records", 0);
			frm.set_value("failed_records", 0);
		}

		frm.add_custom_button(__("Process Data"), () => process_ppas_paste_data(frm), __("Actions"));
		frm.add_custom_button(
			__("Import Valid Records"),
			() => import_ppas_valid_records(frm),
			__("Actions")
		);
	},
});

function process_ppas_paste_data(frm) {
	if (!frm.doc.season) {
		frappe.msgprint({
			title: __("Season required"),
			message: __("Please select Season before processing."),
			indicator: "orange",
		});
		return;
	}

	if (!frm.doc.paste_data || !String(frm.doc.paste_data).trim()) {
		frappe.msgprint({
			title: __("No data"),
			message: __("Paste PPAS table data first."),
			indicator: "orange",
		});
		return;
	}

	frappe.call({
		method: "ivri_od.procurement.doctype.ppas_transit_pass_import.ppas_transit_pass_import.process_paste",
		args: {
			season: frm.doc.season,
			miller: frm.doc.miller,
			paste_data: frm.doc.paste_data,
		},
		freeze: true,
		freeze_message: __("Processing pasted PPAS data..."),
		callback(r) {
			const result = r.message || {};
			const items = result.items || [];

			frm.clear_table("import_items");
			for (const row of items) {
				const child = frm.add_child("import_items");
				Object.assign(child, row);
			}

			frm.set_value("total_records", result.total_records || 0);
			frm.set_value("duplicate_records", result.duplicate_records || 0);
			frm.set_value("failed_records", result.failed_records || 0);
			frm.refresh_field("import_items");
			frm.refresh_fields();

			if (!items.length) {
				frappe.msgprint({
					title: __("Processing"),
					message: __("No rows were parsed from the pasted data."),
					indicator: "orange",
				});
				return;
			}

			frappe.msgprint({
				title: __("Processing Complete"),
				message: `
					<b>Total Records:</b> ${result.total_records || 0}<br>
					<b>Duplicate Records:</b> ${result.duplicate_records || 0}<br>
					<b>Failed Records:</b> ${result.failed_records || 0}
				`,
				indicator: (result.failed_records || 0) > 0 ? "orange" : "green",
			});

			if (frm.is_dirty()) {
				frm.save();
			}
		},
	});
}

function import_ppas_valid_records(frm) {
	if (!frm.doc.season) {
		frappe.msgprint({
			title: __("Season required"),
			message: __("Please select Season."),
			indicator: "orange",
		});
		return;
	}

	const valid_items = (frm.doc.import_items || []).filter((row) => row.row_status === "Valid");
	if (!valid_items.length) {
		frappe.msgprint({
			title: __("Nothing to import"),
			message: __("No valid rows. Run Process Data first."),
			indicator: "orange",
		});
		return;
	}

	frappe.call({
		method: "ivri_od.procurement.doctype.ppas_transit_pass_import.ppas_transit_pass_import.import_valid_rows",
		args: {
			season: frm.doc.season,
			items_json: JSON.stringify(valid_items),
		},
		freeze: true,
		freeze_message: __("Importing valid PPAS rows..."),
		callback(r) {
			const summary = r.message || {};
			const imported = summary.imported || 0;
			const updated = summary.updated || 0;
			const failed = summary.failed || 0;

			frappe.msgprint({
				title: __("Import Complete"),
				message: `
					<b>New:</b> ${imported}<br>
					<b>Updated:</b> ${updated}<br>
					<b>Failed:</b> ${failed}<br><br>
					<a href="/app/ppas-transit-pass">Open PPAS Transit Pass</a>
				`,
				indicator: failed > 0 ? "orange" : "green",
			});

			process_ppas_paste_data(frm);
		},
	});
}
