// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

const GATE_ENTRY_PASS_BTN = "btn-gate-entry-pass";

frappe.listview_settings["Gate Entry"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Inside Mill"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Gate Entry", "in_out", "=", "In"],
				["Gate Entry", "inside_mill", "=", 1],
			]);
		});
	},
};

frappe.ui.form.on("Gate Entry", {
	refresh(frm) {
		frm.set_df_property("in_out", "hidden", 1);
		set_weighment_flag(frm);
		attach_gate_entry_pass_buttons(frm);
	},
	in_purpose(frm) {
		set_weighment_flag(frm);
	},
});

$(document).on("form-refresh", (e, frm) => {
	if (frm && frm.doctype === "Gate Entry") {
		attach_gate_entry_pass_buttons(frm);
	}
});

function attach_gate_entry_pass_buttons(frm) {
	if (!frm || !frm.page || !frm.page.inner_toolbar) {
		return;
	}

	frm.page.inner_toolbar.find(`.${GATE_ENTRY_PASS_BTN}`).remove();
	const $toolbar = frm.page.inner_toolbar.removeClass("hide");

	$(
		`<button type="button" class="btn btn-primary btn-sm ellipsis ${GATE_ENTRY_PASS_BTN}"></button>`
	)
		.text(__("Print Pass"))
		.on("click", () => print_gate_entry_pass(frm))
		.appendTo($toolbar);

	$(
		`<button type="button" class="btn btn-default btn-sm ellipsis ${GATE_ENTRY_PASS_BTN}"></button>`
	)
		.text(__("Download PDF"))
		.on("click", () => download_gate_entry_pass_pdf(frm))
		.appendTo($toolbar);
}

function gate_entry_pass_name(frm) {
	return (frm.doc.name || "").trim();
}

function ensure_gate_entry_saved(frm) {
	if (frm.is_new() || !gate_entry_pass_name(frm)) {
		frappe.msgprint({
			title: __("Save required"),
			message: __("Save this Gate Entry first, then print or download the pass with QR code."),
			indicator: "orange",
		});
		return false;
	}
	return true;
}

function print_gate_entry_pass(frm) {
	if (!ensure_gate_entry_saved(frm)) {
		return;
	}
	const name = gate_entry_pass_name(frm);
	frappe.call({
		method: "ivri_od.procurement.doctype.gate_entry.gate_entry.get_gate_entry_pass_html",
		args: { name },
		freeze: true,
		freeze_message: __("Preparing pass…"),
		callback(r) {
			if (!r.message) {
				frappe.msgprint({
					message: __("Could not generate gate pass."),
					indicator: "red",
				});
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

function download_gate_entry_pass_pdf(frm) {
	if (!ensure_gate_entry_saved(frm)) {
		return;
	}
	const name = gate_entry_pass_name(frm);
	const url =
		frappe.urllib.get_full_url(
			"/api/method/ivri_od.procurement.doctype.gate_entry.gate_entry.download_gate_entry_pass_pdf"
		) +
		"?name=" +
		encodeURIComponent(name);
	window.open(url, "_blank");
}

function set_weighment_flag(frm) {
	const automatic = ["Paddy", "Rice"].includes(frm.doc.in_purpose);
	const is_gate_in = frm.doc.in_out === "In";
	frm.set_df_property("going_to_weighment", "read_only", automatic || !is_gate_in);
	if (automatic && !cint(frm.doc.going_to_weighment)) {
		frm.set_value("going_to_weighment", 1);
	} else if (!is_gate_in && cint(frm.doc.going_to_weighment)) {
		frm.set_value("going_to_weighment", 0);
	}
}
