// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Local Paddy Purchase Order", {
	refresh(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__("Refresh Quantities"), () => {
				frappe.call({
					method: "ivri_od.procurement.doctype.local_paddy_purchase_order.local_paddy_purchase_order.refresh_po_quantities",
					args: { po_name: frm.doc.name },
					callback(r) {
						if (r.message) {
							frm.reload_doc();
							frappe.show_alert({
								message: __("Quantities refreshed successfully."),
								indicator: "green",
							});
						}
					},
				});
			});

			if (frm.doc.status !== "Closed") {
				frm.add_custom_button(__("Close Order"), () => {
					frappe.confirm(__("Are you sure you want to close this Purchase Order?"), () => {
						frappe.call({
							method: "ivri_od.procurement.doctype.local_paddy_purchase_order.local_paddy_purchase_order.close_purchase_order",
							args: { po_name: frm.doc.name },
							callback() {
								frm.reload_doc();
							},
						});
					});
				}, __("Status"));
			} else {
				frm.add_custom_button(__("Re-open Order"), () => {
					frappe.call({
						method: "ivri_od.procurement.doctype.local_paddy_purchase_order.local_paddy_purchase_order.reopen_purchase_order",
						args: { po_name: frm.doc.name },
						callback() {
							frm.reload_doc();
						},
					});
				}, __("Status"));
			}
		}

		frm.page.set_indicator(get_po_status_color(frm.doc.status), frm.doc.status);
	},
	ordered_quantity(frm) {
		calculate_pending(frm);
	},
	received_quantity(frm) {
		calculate_pending(frm);
	},
});

function calculate_pending(frm) {
	const ordered = flt(frm.doc.ordered_quantity);
	const received = flt(frm.doc.received_quantity);
	frm.set_value("pending_quantity", Math.max(ordered - received, 0));
}

function get_po_status_color(status) {
	switch (status) {
		case "Open":
			return "blue";
		case "Partially Received":
			return "orange";
		case "Completed":
			return "green";
		case "Closed":
			return "darkgrey";
		default:
			return "gray";
	}
}
