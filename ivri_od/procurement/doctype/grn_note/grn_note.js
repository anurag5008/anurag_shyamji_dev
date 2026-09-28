// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("GRN Note", {
	onload(frm) {
		setup_pass_unique_key_autocomplete(frm);
		setup_rst_no_autocomplete(frm);
		sync_grn_no_display(frm);
	},
	refresh(frm) {
		setup_pass_unique_key_autocomplete(frm);
		setup_rst_no_autocomplete(frm);
		setup_qc_bag_details_grid(frm);
		setup_entry_details_grid(frm);
		sync_grn_no_display(frm);
	},
	pass_unique_key(frm) {
		load_transit_pass_details(frm);
		setup_rst_no_autocomplete(frm, true);
		if (frm.doc.rst_no) {
			load_rst_details(frm);
		}
	},
	rst_no(frm) {
		load_rst_details(frm);
	},
});

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
			frm.set_value("transit_pass_no", data.transit_pass_no || "");
			frm.set_value("transit_pass_date", data.transit_pass_date || "");
			frm.set_value("tp_quantity", data.tp_quantity || 0);
			frm.set_value("pacs", data.pacs || "");
			frm.set_value("ppc", data.ppc || "");
			if (data.entry_details) {
				set_entry_details(frm, data.entry_details);
			}
		},
	});
}

const RST_FETCH_FIELDS = [
	"weigh_bridge_measurement",
	"gross_vehicle_weight",
	"gross_weight",
	"tare_weight",
	"net_weight",
	"gunny_type",
	"gunny_weight",
	"gate_entry",
	"vehicle_no",
	"driver_name",
	"arrival_date",
	"arrival_time",
	"gate_out_time",
	"quality_check",
	"qc_sample_no",
	"no_of_bags",
	"moisture",
	"dust",
	"unloader_name",
	"unloading_point",
	"ppc_name",
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
}

function setup_qc_bag_details_grid(frm) {
	const grid = frm.fields_dict.qc_bag_details?.grid;
	if (!grid || grid._grn_qc_bag_grid_ready) {
		return;
	}
	grid._grn_qc_bag_grid_ready = true;
	grid.wrapper.find(".grid-add-row").hide();
	grid.wrapper.find(".grid-remove-rows").hide();
}

function setup_entry_details_grid(frm) {
	const grid = frm.fields_dict.entry_details?.grid;
	if (!grid || grid._grn_entry_grid_ready) {
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
