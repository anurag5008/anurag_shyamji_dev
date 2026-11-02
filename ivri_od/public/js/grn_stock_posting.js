// Copyright (c) 2026, Profezzo and contributors
// GRN Note: "Post to Stock" for accepted government paddy (see procurement/stock_posting.py).
// Added through hooks.py doctype_js, so the GRN Note's own script is untouched.

frappe.ui.form.on("GRN Note", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}
		frappe.call({
			method: "ivri_od.procurement.stock_posting.get_stock_posting_status",
			args: { grn_name: frm.doc.name },
			callback(r) {
				const status = r.message;
				if (!status || status.is_local) {
					return;
				}
				if (status.posted) {
					frm.dashboard.add_comment(
						__("Posted to stock in {0}.", [
							`<a href="/desk/stock-entry/${encodeURIComponent(status.stock_entry)}">${status.stock_entry}</a>`,
						]),
						"green",
						true
					);
					if (status.drift.length) {
						frm.dashboard.add_comment(
							__("Values changed since posting: {0}", [status.drift.join("; ")]),
							"red",
							true
						);
					}
					if (status.can_post) {
						frm.add_custom_button(
							__("Cancel Stock Posting"),
							() => cancel_posting(frm),
							__("Stock")
						);
					}
				} else if (status.enabled && status.can_post) {
					frm.add_custom_button(__("Post to Stock"), () => post_to_stock(frm, status), __("Stock"));
				}
			},
		});
	},
});

function post_to_stock(frm, status) {
	const dialog = new frappe.ui.Dialog({
		title: __("Post to Stock"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p>${__("Posts the accepted net weight ({0} QT) as a zero-rate Material Receipt. No rate or charge is added.", [
					frm.doc.net_weight,
				])}</p>`,
			},
			{
				fieldname: "warehouse",
				fieldtype: "Link",
				label: __("Warehouse"),
				options: "Warehouse",
				reqd: 1,
				default: status.unloading_warehouse || undefined,
				description: status.unloading_warehouse ? __("From the Quality Check Unloading Point.") : "",
				get_query: () => ({
					filters: {
						is_group: 0,
						disabled: 0,
						company: status.company || undefined,
						// the physical warehouses of the Company; Raw and Boiled share them
						physical_location: ["is", "set"],
					},
				}),
			},
		],
		primary_action_label: __("Post"),
		primary_action(values) {
			frappe.call({
				method: "ivri_od.procurement.stock_posting.post_grn_to_stock",
				args: { grn_name: frm.doc.name, warehouse: values.warehouse },
				freeze: true,
				callback(r) {
					dialog.hide();
					if (r.message) {
						frappe.show_alert({ message: __("Posted in {0}", [r.message]), indicator: "green" });
						frm.reload_doc();
					}
				},
			});
		},
	});
	dialog.show();
}

function cancel_posting(frm) {
	frappe.prompt(
		{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
		(values) => {
			frappe.call({
				method: "ivri_od.procurement.stock_posting.cancel_stock_posting",
				args: { grn_name: frm.doc.name, reason: values.reason },
				freeze: true,
				callback() {
					frm.reload_doc();
				},
			});
		},
		__("Cancel Stock Posting"),
		__("Cancel Posting")
	);
}
