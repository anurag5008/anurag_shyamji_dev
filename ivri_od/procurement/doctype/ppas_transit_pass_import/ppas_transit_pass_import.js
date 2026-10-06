// Copyright (c) 2026, Profezzo and contributors

frappe.ui.form.on("PPAS Transit Pass Import", {
	refresh(frm) {
		frm.page.clear_primary_action();

		frm.add_custom_button(__("Process Data"), () => process_ppas_paste_data(frm));

		if (!frm.is_new()) {
			frm.add_custom_button(
				__("Push to PPAS Transit Pass"),
				() => push_to_ppas_transit_pass(frm),
				__("Actions")
			);
		}

		if (frm.doc.import_items && frm.doc.import_items.length) {
			frm.dashboard.set_headline(
				__(
					"{0} row(s) in Import Items — use <b>Push to PPAS Transit Pass</b> only when ready.",
					[frm.doc.import_items.length]
				)
			);
		}
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
			message: __("Paste PPAS table data in the box above, then click Process Data."),
			indicator: "orange",
		});
		return;
	}

	frappe.call({
		method:
			"ivri_od.procurement.doctype.ppas_transit_pass_import.ppas_transit_pass_import.process_and_save_import",
		args: {
			name: frm.is_new() ? null : frm.doc.name,
			season: frm.doc.season,
			miller: frm.doc.miller,
			paste_data: frm.doc.paste_data,
		},
		freeze: true,
		freeze_message: __("Processing pasted PPAS data..."),
		callback(r) {
			const result = r.message || {};

			if (result.name && frm.doc.name !== result.name) {
				frappe.set_route("Form", "PPAS Transit Pass Import", result.name);
				return;
			}

			frm.reload_doc().then(() => {
				frappe.msgprint({
					title: __("Processing Complete"),
					message: `
						<b>Total Records:</b> ${result.total_records || 0}<br>
						<b>Duplicate Records:</b> ${result.duplicate_records || 0}<br>
						<b>Failed Records:</b> ${result.failed_records || 0}<br>
						<b>Import Items:</b> ${result.item_count || 0} row(s) saved on this document.
					`,
					indicator: (result.failed_records || 0) > 0 ? "orange" : "green",
				});
			});
		},
	});
}

function push_to_ppas_transit_pass(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint({
			title: __("Save first"),
			message: __("Save the document before pushing to PPAS Transit Pass."),
			indicator: "orange",
		});
		return;
	}

	const valid_count = (frm.doc.import_items || []).filter((row) => row.row_status === "Valid").length;
	if (!valid_count) {
		frappe.msgprint({
			title: __("Nothing to push"),
			message: __("No valid rows. Click Process Data after pasting PPAS rows."),
			indicator: "orange",
		});
		return;
	}

	frappe.confirm(
		__(
			"Create {0} PPAS Transit Pass record(s) from valid rows? Duplicates and failed rows are skipped.",
			[valid_count]
		),
		() => {
			frappe.call({
				method:
					"ivri_od.procurement.doctype.ppas_transit_pass_import.ppas_transit_pass_import.push_valid_to_transit_pass",
				args: { name: frm.doc.name },
				freeze: true,
				freeze_message: __("Pushing to PPAS Transit Pass..."),
				callback(r) {
					const summary = r.message || {};
					frappe.msgprint({
						title: __("Push Complete"),
						message: `
							<b>New:</b> ${summary.imported || 0}<br>
							<b>Updated:</b> ${summary.updated || 0}<br>
							<b>Failed:</b> ${summary.failed || 0}<br><br>
							<a href="/app/ppas-transit-pass">Open PPAS Transit Pass list</a>
						`,
						indicator: (summary.failed || 0) > 0 ? "orange" : "green",
					});
					frm.reload_doc();
				},
			});
		}
	);
}
