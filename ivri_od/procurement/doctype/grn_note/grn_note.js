// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

const GRN_NOTE_PASS_BTN = "btn-grn-note-pass";

frappe.dom.set_style(`
	.form-section[data-fieldname="entry_data_section"].empty-section:not(.hide-control) {
		display: block !important;
	}
	.form-section[data-fieldname="entry_data_section"]:not(.hide-control) .section-head {
		display: block !important;
	}
	[data-fieldname="qc_bag_details"] .grid-heading-row,
	[data-fieldname="bag_weight_details"] .grid-heading-row,
	[data-fieldname="type_of_pkt"] .grid-heading-row {
		height: auto !important;
		min-height: 32px;
	}
	[data-fieldname="qc_bag_details"] .grid-heading-row .grid-row,
	[data-fieldname="bag_weight_details"] .grid-heading-row .grid-row,
	[data-fieldname="type_of_pkt"] .grid-heading-row .grid-row {
		height: auto !important;
		min-height: 32px;
	}
	[data-fieldname="qc_bag_details"] .grid-heading-row .grid-static-col,
	[data-fieldname="bag_weight_details"] .grid-heading-row .grid-static-col,
	[data-fieldname="type_of_pkt"] .grid-heading-row .grid-static-col,
	.grid-heading-row .grid-static-col[data-fieldname="jute_pkt_no"],
	.grid-heading-row .grid-static-col[data-fieldname="no_of_plastic_bag"],
	.grid-heading-row .grid-static-col[data-fieldname="jute_bags"],
	.grid-heading-row .grid-static-col[data-fieldname="plastic_bags"],
	.grid-heading-row .grid-static-col[data-fieldname="total_bags"] {
		height: auto !important;
		min-height: 32px;
		padding-top: 6px !important;
		padding-bottom: 6px !important;
		white-space: normal !important;
	}
	[data-fieldname="qc_bag_details"] .grid-heading-row .static-area,
	[data-fieldname="bag_weight_details"] .grid-heading-row .static-area,
	[data-fieldname="type_of_pkt"] .grid-heading-row .static-area,
	.grid-heading-row .grid-static-col[data-fieldname="jute_pkt_no"] .static-area,
	.grid-heading-row .grid-static-col[data-fieldname="no_of_plastic_bag"] .static-area,
	.grid-heading-row .grid-static-col[data-fieldname="jute_bags"] .static-area,
	.grid-heading-row .grid-static-col[data-fieldname="plastic_bags"] .static-area,
	.grid-heading-row .grid-static-col[data-fieldname="total_bags"] .static-area {
		white-space: normal !important;
		word-break: normal !important;
		overflow: visible !important;
		text-overflow: unset !important;
		line-height: 1.25 !important;
	}
`);

frappe.ui.form.on("GRN Note", {
	onload(frm) {
		setup_pass_unique_key_autocomplete(frm);
		setup_rst_no_autocomplete(frm);
		sync_grn_no_display(frm);
		sync_section_visibility(frm);
		setup_entry_details_grid(frm);
		sync_entry_details_display(frm);
	},
	refresh(frm) {
		frm.toggle_display("is_local_procurement", Boolean(frm.doc.is_local_procurement));
		frm.toggle_display("local_purchase_order", Boolean(frm.doc.local_purchase_order));
		setup_pass_unique_key_autocomplete(frm);
		setup_rst_no_autocomplete(frm);
		setup_qc_bag_details_grid(frm);
		setup_old_new_bags_grid(frm);
		setup_entry_details_grid(frm);
		sync_grn_no_display(frm);
		sync_purchase_heading(frm);
		sync_gate_exit_fields(frm);
		sync_tp_fulfillment_display(frm);
		sync_section_visibility(frm);
		sync_entry_details_display(frm);
		attach_grn_note_pass_buttons(frm);
		if (!frm.doc.is_local_procurement && (frm.doc.pass_unique_key || "").trim() && !(frm.doc.mill_name || "").trim()) {
			load_transit_pass_details(frm);
		}
	},
	pass_unique_key(frm) {
		const key = (frm.doc.pass_unique_key || "").trim();
		if (!key && frm.is_new()) {
			frm.set_value("mill_name", "");
			frm.set_value("chhatni", 0);
		}
		load_transit_pass_details(frm);
		setup_rst_no_autocomplete(frm, true);
		if (frm.doc.rst_no) {
			load_rst_details(frm);
		}
	},
	rst_no(frm) {
		load_rst_details(frm);
	},
	party_name(frm) {
		// Local procurement pending RST lookup is disabled
	},
	ppc_name(frm) {
		if (frm.is_new()) {
			refresh_grn_chhatni(frm);
		}
	},
	entry_details_add(frm) {
		sync_entry_details_display(frm);
	},
	entry_details_remove(frm) {
		sync_entry_details_display(frm);
	},
});

$(document).on("form-refresh", (e, frm) => {
	if (frm && frm.doctype === "GRN Note") {
		attach_grn_note_pass_buttons(frm);
	}
});

function attach_grn_note_pass_buttons(frm) {
	if (!frm || !frm.page || !frm.page.inner_toolbar) {
		return;
	}
	frm.page.inner_toolbar.find(`.${GRN_NOTE_PASS_BTN}`).remove();
	const $toolbar = frm.page.inner_toolbar.removeClass("hide");

	$(
		`<button type="button" class="btn btn-primary btn-sm ellipsis ${GRN_NOTE_PASS_BTN}"></button>`
	)
		.text(__("Print GRN"))
		.on("click", () => print_grn_note_pass(frm))
		.appendTo($toolbar);

	$(
		`<button type="button" class="btn btn-default btn-sm ellipsis ${GRN_NOTE_PASS_BTN}"></button>`
	)
		.text(__("Download PDF"))
		.on("click", () => download_grn_note_pass_pdf(frm))
		.appendTo($toolbar);
}

function ensure_grn_note_saved(frm) {
	if (frm.is_new() || !(frm.doc.name || "").trim()) {
		frappe.msgprint({
			title: __("Save required"),
			message: __("Save this GRN first, then print or download with QR code."),
			indicator: "orange",
		});
		return false;
	}
	return true;
}

function print_grn_note_pass(frm) {
	if (!ensure_grn_note_saved(frm)) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.grn_note.grn_note.get_grn_note_pass_html",
		args: { name: frm.doc.name },
		freeze: true,
		freeze_message: __("Preparing GRN…"),
		callback(r) {
			if (!r.message) {
				frappe.msgprint({
					message: __("Could not generate GRN print."),
					indicator: "red",
				});
				return;
			}
			const win = window.open("", "_blank");
			if (!win) {
				frappe.msgprint({
					title: __("Popup blocked"),
					message: __("Allow popups to print the GRN."),
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

function download_grn_note_pass_pdf(frm) {
	if (!ensure_grn_note_saved(frm)) {
		return;
	}
	const url =
		frappe.urllib.get_full_url(
			"/api/method/ivri_od.procurement.doctype.grn_note.grn_note.download_grn_note_pass_pdf"
		) +
		"?name=" +
		encodeURIComponent(frm.doc.name);
	window.open(url, "_blank");
}

function sync_gate_exit_fields(frm) {
	if (frm.is_new() || !frm.doc.name || frm._gate_exit_synced) {
		return;
	}
	frm._gate_exit_synced = true;
	frappe.call({
		method: "ivri_od.procurement.doctype.grn_note.grn_note.sync_gate_exit_on_grn",
		args: { grn_name: frm.doc.name },
		callback(r) {
			const data = r.message || {};
			const changed = ["gate_exit", "gate_exit_datetime", "party_name", "mobile_no"].some(
				(fieldname) => (frm.doc[fieldname] || "") !== (data[fieldname] || "")
			);
			if (changed) {
				frm.reload_doc();
			}
		},
	});
}

function sync_purchase_heading(frm) {
	const local = !!frm.doc.is_local_procurement;
	const heading = local ? __("Local Paddy Purchase") : __("Government Paddy Purchase");
	frm.set_df_property("grn_section", "label", local ? __("GRN") : heading);

	const section = frm.fields_dict.grn_section;
	const head = section && (section.head || (section.wrapper && section.wrapper.find(".section-head")));
	if (head && head.length) {
		head.html(local ? __("GRN") : heading);
		head.css(
			local
				? {}
				: {
						"font-size": "22px",
						"font-weight": "700",
					}
		);
	}

	const banner = frm.fields_dict.local_paddy_heading;
	if (!banner) {
		return;
	}
	banner.$wrapper.find(".control-label").hide();
	banner.$wrapper.find(".html-content, .control-input-wrapper, .form-group").first().html(
		`<div style="font-size:32px;font-weight:700;line-height:1.15;margin:8px 0 16px;">${frappe.utils.escape_html(
			heading
		)}</div>`
	);
	banner.$wrapper.toggle(!!local);
}

function sync_grn_no_display(frm) {
	if (frm.is_new() && !(frm.doc.grn_no || "").trim()) {
		frm.set_df_property(
			"grn_no",
			"description",
			__(
				"Assigned on save: GRN-{year}-{number} (year from receipt date, e.g. GRN-2026-00001)."
			)
		);
	} else if ((frm.doc.grn_no || "").trim()) {
		frm.set_df_property("grn_no", "description", "");
	}
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

function setup_rst_no_autocomplete(frm, force = false) {
	const field = frm.fields_dict.rst_no;
	if (!field) {
		return;
	}
	if (field.rst_no_autocomplete_setup && !force) {
		return;
	}
	field.rst_no_autocomplete_setup = true;

	const load_options = (txt = "") => {
		frappe.call({
			method: "ivri_od.procurement.doctype.grn_note.grn_note.get_rst_no_autocomplete",
			args: {
				txt,
				pass_unique_key: frm.doc.pass_unique_key || "",
				limit: 25,
			},
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
	frappe.call({
		method: "ivri_od.procurement.doctype.grn_note.grn_note.get_transit_pass_details",
		args: { pass_unique_key: key },
		callback(r) {
			const data = r.message || {};
			if (!data || data.error) {
				return;
			}
			frm.set_value("cmr_season", data.cmr_season || "");
			frm.set_value("mill_name", data.mill_name || "");
			if (frm.is_new()) {
				frm.set_value("chhatni", data.chhatni || 0);
			}
			frm.set_value("transit_pass_no", data.transit_pass_no || "");
			frm.set_value("transit_pass_datetime", data.transit_pass_datetime || "");
			frm.set_value("transit_pass_date", data.transit_pass_date || "");
			frm.set_value("tp_quantity", data.tp_quantity || 0);
			frm.set_value("pacs", data.pacs || "");
			frm.set_value("ppc", data.ppc || "");
			if (data.entry_details) {
				set_entry_details(frm, data.entry_details);
			}
			if (frm.is_new()) {
				refresh_grn_chhatni(frm);
			}
		},
	});
}

function refresh_grn_chhatni(frm) {
	if (!frm.is_new() || frm.doc.is_local_procurement) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.grn_note.grn_note.fetch_chhatni_for_grn",
		args: {
			pass_unique_key: frm.doc.pass_unique_key || "",
			mill_name: frm.doc.mill_name || "",
			ppc: frm.doc.ppc || "",
			ppc_name: frm.doc.ppc_name || "",
			cmr_season: frm.doc.cmr_season || "",
		},
		callback(r) {
			frm.set_value("chhatni", flt(r.message));
		},
	});
}

const RST_FETCH_FIELDS = [
	"is_local_procurement",
	"local_procurement_note",
	"weigh_bridge_measurement",
	"gross_vehicle_weight",
	"gross_weight",
	"tare_weight",
	"deduction",
	"net_weight",
	"gunny_type",
	"gunny_weight",
	"jute_bags",
	"plastic_bags",
	"total_bags",
	"gate_entry",
	"vehicle_no",
	"driver_name",
	"mobile_no",
	"party_name",
	"receipt_datetime",
	"arrival_datetime",
	"gate_exit",
	"gate_exit_datetime",
	"quality_check",
	"qc_datetime",
	"qc_sample_no",
	"no_of_bags",
	"moisture",
	"dust",
	"unloader_name",
	"unloading_point",
	"ppc_name",
	"is_farmer_or_agent",
	"agent_name",
	"paddy_type",
	"paddy_quality",
	"qc_decision",
	"paddy_received_in_pkt",
	"paddy_returned",
];

function load_rst_details(frm) {
	const rst_no = (frm.doc.rst_no || "").trim();
	if (!rst_no) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.grn_note.grn_note.get_grn_details_from_rst",
		args: {
			rst_no,
			pass_unique_key: frm.doc.pass_unique_key || "",
		},
		callback(r) {
			const data = r.message || {};
			if (data.error) {
				frappe.msgprint({
					title: __("RST No"),
					message: data.error,
					indicator: "orange",
				});
				return;
			}
			apply_rst_fetch_data(frm, data);
		},
	});
}

async function apply_rst_fetch_data(frm, data) {
	const qc_link_fields = ["quality_check", "ppc_name"];
	const other_fields = RST_FETCH_FIELDS.filter((f) => !qc_link_fields.includes(f));

	for (const fieldname of other_fields) {
		if (data[fieldname] !== undefined) {
			await frm.set_value(fieldname, data[fieldname]);
		}
	}
	if (data.quality_check !== undefined) {
		await frm.set_value("quality_check", data.quality_check);
	}
	if (data.ppc_name !== undefined) {
		await frm.set_value("ppc_name", data.ppc_name);
	} else if (data.quality_check) {
		await frm.trigger("quality_check");
	}
	if (data.qc_bag_details) {
		set_qc_bag_details(frm, data.qc_bag_details);
	}
	if (data.old_new_bags) {
		set_old_new_bags(frm, data.old_new_bags);
	}
	if (frm.is_new()) {
		refresh_grn_chhatni(frm);
	}
	sync_purchase_heading(frm);
}

function sync_tp_fulfillment_display(frm) {
	if (frm.is_new() || frm.doc.is_local_procurement || !(frm.doc.pass_unique_key || "").trim() || !frm.doc.name) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.grn_note.grn_note.refresh_tp_fulfillment_on_grn",
		args: { name: frm.doc.name },
		callback(r) {
			const d = r.message || {};
			for (const fieldname of [
				"received_quantity",
				"tp_cumulative_received",
				"tp_chhatni_balance",
				"chhatni_received_pct",
				"tp_cumulative_deduction",
				"tp_fulfillment_status",
				"chhatni_fulfillment_status",
				"chhatni_fulfillment_remark",
			]) {
				if (d[fieldname] !== undefined && d[fieldname] !== null) {
					frm.set_value(fieldname, d[fieldname]);
				}
			}
		},
	});
}

function setup_qc_bag_details_grid(frm) {
	lock_child_grid(frm.fields_dict.qc_bag_details?.grid, "_grn_qc_bag_grid_ready");
}

function setup_old_new_bags_grid(frm) {
	lock_child_grid(frm.fields_dict.old_new_bags?.grid, "_grn_old_new_bags_ready");
}

function lock_child_grid(grid, flag) {
	if (!grid || grid[flag]) {
		return;
	}
	grid[flag] = true;
	grid.wrapper.find(".grid-add-row").hide();
	grid.wrapper.find(".grid-remove-rows").hide();
}

function sync_section_visibility(frm) {
	frm.set_df_property("paddy_bags_section", "hidden", 1);
	frm.set_df_property("old_new_bags", "hidden", 1);
}

function sync_entry_details_display(frm) {
	if (frm.fields_dict.entry_data_section && frm.fields_dict.entry_data_section.collapse) {
		frm.fields_dict.entry_data_section.collapse(false);
	}
	const has_records = (frm.doc.entry_details || []).length > 0;
	frm.set_df_property("entry_details", "hidden", has_records ? 0 : 1);
	if (!has_records && frm.fields_dict.entry_data_section?.wrapper) {
		frm.fields_dict.entry_data_section.wrapper.removeClass("empty-section");
		if (!frm.doc.is_local_procurement) {
			frm.fields_dict.entry_data_section.wrapper.show();
			frm.fields_dict.entry_data_section.wrapper.find(".section-head").show();
		}
	}
}

function setup_entry_details_grid(frm) {
	const grid = frm.fields_dict.entry_details?.grid;
	if (!grid) {
		return;
	}
	grid.set_column_disp(["entry_date", "entry_time"], false);
	if (grid._grn_entry_grid_ready) {
		return;
	}
	grid._grn_entry_grid_ready = true;
	grid.wrapper.find(".grid-add-row").hide();
	grid.wrapper.find(".grid-remove-rows").hide();
}

function set_entry_details(frm, rows) {
	frm.clear_table("entry_details");
	(rows || []).forEach((row) => {
		const child = frm.add_child("entry_details");
		child.entry = row.entry || "";
		child.entry_date = row.entry_date || "";
		child.entry_time = row.entry_time || "";
		child.agent_name = row.agent_name || "";
		child.pacs_name = row.pacs_name || "";
		child.entry_quantity = row.entry_quantity || 0;
		child.entry_price_per_quintal = row.entry_price_per_quintal || 0;
		child.total_amount = row.total_amount || 0;
	});
	frm.refresh_field("entry_details");
	setup_entry_details_grid(frm);
	sync_entry_details_display(frm);
}

function set_qc_bag_details(frm, rows) {
	frm.clear_table("qc_bag_details");
	(rows || []).forEach((row) => {
		const child = frm.add_child("qc_bag_details");
		child.jute_pkt_no = row.jute_pkt_no || 0;
		child.no_of_plastic_bag = row.no_of_plastic_bag || 0;
	});
	frm.refresh_field("qc_bag_details");
	setup_qc_bag_details_grid(frm);
}

function set_old_new_bags(frm, rows) {
	frm.clear_table("old_new_bags");
	(rows || []).forEach((row) => {
		const child = frm.add_child("old_new_bags");
		child.old_bags = row.old_bags || 0;
		child.new_bags = row.new_bags || 0;
	});
	frm.refresh_field("old_new_bags");
	setup_old_new_bags_grid(frm);
}

