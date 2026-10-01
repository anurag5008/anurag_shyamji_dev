// Copyright (c) 2026, Profezzo and contributors
// Shared helpers for Gate Entry / Gate Exit pass (also used by Client Script patch)

/* eslint-disable no-unused-vars */

function ivri_od_open_gate_pass(name) {
	if (!name) {
		frappe.msgprint({
			title: __("Save required"),
			message: __("Save this document first, then print the gate pass."),
			indicator: "orange",
		});
		return;
	}
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
					message: __("Allow popups for this site to print the gate pass."),
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

function ivri_od_download_gate_pass(name) {
	if (!name) {
		frappe.msgprint({
			title: __("Save required"),
			message: __("Save this document first, then download the gate pass."),
			indicator: "orange",
		});
		return;
	}
	window.open(
		frappe.urllib.get_full_url(
			"/api/method/ivri_od.procurement.doctype.gate_entry.gate_entry.download_gate_entry_pass"
		) +
			"?name=" +
			encodeURIComponent(name),
		"_blank"
	);
}

function ivri_od_attach_gate_pass_toolbar(frm, get_gate_entry_name) {
	if (!frm || !frm.page || !frm.page.inner_toolbar) {
		return;
	}

	const resolve_name = () => {
		if (typeof get_gate_entry_name === "function") {
			return (get_gate_entry_name() || "").trim();
		}
		return (frm.doc.name || "").trim();
	};

	frm.page.inner_toolbar.find(".ivri-gate-pass-btn").remove();

	const $toolbar = frm.page.inner_toolbar.removeClass("hide");

	$(
		`<button type="button" class="btn btn-primary btn-sm ellipsis ivri-gate-pass-btn"></button>`
	)
		.text(__("Print Pass"))
		.on("click", () => ivri_od_open_gate_pass(resolve_name()))
		.appendTo($toolbar);

	$(
		`<button type="button" class="btn btn-default btn-sm ellipsis ivri-gate-pass-btn"></button>`
	)
		.text(__("Download Pass"))
		.on("click", () => ivri_od_download_gate_pass(resolve_name()))
		.appendTo($toolbar);
}

function ivri_od_schedule_gate_pass_buttons(frm, get_gate_entry_name) {
	const attach = () => ivri_od_attach_gate_pass_toolbar(frm, get_gate_entry_name);
	attach();
	setTimeout(attach, 0);
	setTimeout(attach, 300);
}
