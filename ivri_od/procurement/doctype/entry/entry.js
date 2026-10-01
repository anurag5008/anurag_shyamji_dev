// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

const ENTRY_PASS_BTN = "btn-entry-pass";

frappe.ui.form.on("Entry", {
	onload(frm) {
		setup_pass_unique_key_autocomplete(frm);
	},
	refresh(frm) {
		setup_pass_unique_key_autocomplete(frm);
		attach_entry_pass_buttons(frm);
	},
	pass_unique_key(frm) {
		load_transit_pass_details(frm);
	},
	entry_quantity(frm) {
		update_total_amount(frm);
	},
	entry_price_per_quintal(frm) {
		update_total_amount(frm);
	},
});

$(document).on("form-refresh", (e, frm) => {
	if (frm && frm.doctype === "Entry") {
		attach_entry_pass_buttons(frm);
	}
});

function attach_entry_pass_buttons(frm) {
	if (!frm || !frm.page || !frm.page.inner_toolbar) {
		return;
	}
	frm.page.inner_toolbar.find(`.${ENTRY_PASS_BTN}`).remove();
	const $toolbar = frm.page.inner_toolbar.removeClass("hide");

	$(
		`<button type="button" class="btn btn-primary btn-sm ellipsis ${ENTRY_PASS_BTN}"></button>`
	)
		.text(__("Print Pass"))
		.on("click", () => print_entry_pass(frm))
		.appendTo($toolbar);

	$(
		`<button type="button" class="btn btn-default btn-sm ellipsis ${ENTRY_PASS_BTN}"></button>`
	)
		.text(__("Download PDF"))
		.on("click", () => download_entry_pass_pdf(frm))
		.appendTo($toolbar);
}

function ensure_entry_saved(frm) {
	if (frm.is_new() || !(frm.doc.name || "").trim()) {
		frappe.msgprint({
			title: __("Save required"),
			message: __("Save this Entry first, then print or download the pass with QR code."),
			indicator: "orange",
		});
		return false;
	}
	return true;
}

function print_entry_pass(frm) {
	if (!ensure_entry_saved(frm)) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.entry.entry.get_entry_pass_html",
		args: { name: frm.doc.name },
		freeze: true,
		freeze_message: __("Preparing pass…"),
		callback(r) {
			if (!r.message) {
				frappe.msgprint({ message: __("Could not generate entry pass."), indicator: "red" });
				return;
			}
			const win = window.open("", "_blank");
			if (!win) {
				frappe.msgprint({
					title: __("Popup blocked"),
					message: __("Allow popups to print the pass."),
					indicator: "orange",
				});
				return;
			}
			win.document.open();
			win.document.write(r.message);
			win.document.close();
		},
	});
}

function download_entry_pass_pdf(frm) {
	if (!ensure_entry_saved(frm)) {
		return;
	}
	const url =
		frappe.urllib.get_full_url(
			"/api/method/ivri_od.procurement.doctype.entry.entry.download_entry_pass_pdf"
		) +
		"?name=" +
		encodeURIComponent(frm.doc.name);
	window.open(url, "_blank");
}

function setup_pass_unique_key_autocomplete(frm) {
	const field = frm.fields_dict.pass_unique_key;
	if (!field || field.pass_unique_key_autocomplete_setup) {
		return;
	}
	field.pass_unique_key_autocomplete_setup = true;

	const load_options = (txt = "") => {
		frappe.call({
			method:
				"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.get_pass_unique_key_autocomplete",
			args: { txt, limit: 25 },
			callback(r) {
				if (field.set_data) {
					field.set_data(r.message || []);
				}
			},
		});
	};

	load_options("");
	field.$input?.on("focus", () => load_options(field.get_value() || ""));
	field.$input?.on(
		"input",
		frappe.utils.debounce(() => load_options(field.$input.val() || ""), 300)
	);
}

function load_transit_pass_details(frm) {
	const key = (frm.doc.pass_unique_key || "").trim();
	if (!key) {
		return;
	}
	frappe.db.get_value(
		"PPAS Transit Pass",
		{ pass_unique_key: key },
		["transit_pass_no", "quantity", "pacs"],
		(r) => {
			if (!r) {
				return;
			}
			if (r.transit_pass_no) {
				frm.set_value("transit_pass_no", r.transit_pass_no);
			}
			frm.set_value("tp_quantity", r.quantity || 0);
			frm.set_value("pacs_name", r.pacs || "");
		}
	);
}

function update_total_amount(frm) {
	const total =
		frappe.utils.flt(frm.doc.entry_quantity) *
		frappe.utils.flt(frm.doc.entry_price_per_quintal);
	frm.set_value("total_amount", total);
}
