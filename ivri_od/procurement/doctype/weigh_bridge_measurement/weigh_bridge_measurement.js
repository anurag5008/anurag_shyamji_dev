// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

const KG_PER_QUINTAL = 100;
const QTY_MAX_DECIMALS = 3;

function trimQty(val, maxDecimals = QTY_MAX_DECIMALS) {
	const n = frappe.utils.flt(val, maxDecimals);
	if (!n) {
		return 0;
	}
	return parseFloat(n.toFixed(maxDecimals));
}

/** Exact QT value for totals (3 decimals, no integer rounding). */
function qtyFlt(val) {
	return frappe.utils.flt(val, QTY_MAX_DECIMALS);
}

function inject_wbm_form_styles() {
	if (document.getElementById("wbm-form-compact-css")) {
		return;
	}
	const style = document.createElement("style");
	style.id = "wbm-form-compact-css";
	style.textContent = `
		[data-doctype="Weigh Bridge Measurement"] .form-layout {
			max-width: none;
		}
		[data-doctype="Weigh Bridge Measurement"] .form-section {
			margin-bottom: 0.35rem;
		}
		[data-doctype="Weigh Bridge Measurement"] .section-head.collapsible {
			margin-bottom: 0.25rem;
		}
		[data-doctype="Weigh Bridge Measurement"] .form-column {
			padding-left: 8px;
			padding-right: 8px;
		}
		[data-doctype="Weigh Bridge Measurement"] .grid-field .form-grid {
			margin-left: 0;
		}
	`;
	document.head.appendChild(style);
}

function compact_wbm_form_layout(frm) {
	const layout = frm.layout?.wrapper;
	if (!layout || layout.classList.contains("wbm-compact-applied")) {
		return;
	}
	layout.classList.add("wbm-compact-applied");
	layout.find(".empty-section").hide();
}

frappe.ui.form.on("Weigh Bridge Measurement", {
	onload(frm) {
		inject_wbm_form_styles();
		setup_pass_unique_key_autocomplete(frm);
		setup_farmer_vehicle_autocomplete(frm);
		setup_actual_truck_autocomplete(frm);
		setup_truck_buttons(frm);
		compact_wbm_form_layout(frm);
		sync_quality_from_qc(frm);
	},
	refresh(frm) {
		toggle_wbm_source_mode_ui(frm);
		setup_pass_unique_key_autocomplete(frm);
		setup_farmer_vehicle_autocomplete(frm, true);
		setup_actual_truck_autocomplete(frm, true);
		setup_truck_buttons(frm);
		setup_bag_details_grid(frm);
		setup_refresh_bags_from_qc_button(frm);
		compact_wbm_form_layout(frm);
		sync_quality_from_qc(frm);
	},
	is_farmer_or_agent(frm) {
		clear_wbm_tp_fields(frm);
		toggle_wbm_source_mode_ui(frm);
		setup_farmer_vehicle_autocomplete(frm, true);
		sync_quality_from_qc(frm);
	},
	vehicle_no(frm) {
		const vehicle = (frm.doc.vehicle_no || "").trim().toUpperCase();
		if (vehicle && frm.doc.vehicle_no !== vehicle) {
			frm.set_value("vehicle_no", vehicle);
			return;
		}
		sync_quality_from_qc(frm);
	},
	pass_unique_key(frm) {
		load_transit_pass_details(frm);
	},
	same_truck_as_transit_pass(frm) {
		if (!frm.doc.same_truck_as_transit_pass) {
			frm.set_value("actual_truck_no", "");
		} else {
			setup_actual_truck_autocomplete(frm, true);
		}
		sync_quality_from_qc(frm);
	},
	actual_truck_no(frm) {
		const vehicle = (frm.doc.actual_truck_no || "").trim().toUpperCase();
		if (vehicle && frm.doc.actual_truck_no !== vehicle) {
			frm.set_value("actual_truck_no", vehicle);
			return;
		}
		sync_quality_from_qc(frm);
	},
	truck_no_in_tp(frm) {
		sync_quality_from_qc(frm);
	},
	load_weight(frm) {
		recalculate_weights(frm);
	},
	tare_weight(frm) {
		recalculate_weights(frm);
	},
	deduction(frm) {
		recalculate_weights(frm);
	},
	gunny_type(frm) {
		if (frm.doc.gunny_type !== "Gunny Cut") {
			frm.set_value("gunny_weight", 0);
		} else {
			sync_quality_from_qc(frm);
			frm.refresh_field("bag_weight_details");
		}
		recalculate_weights(frm);
	},
	after_save(frm) {
		sync_quality_from_qc(frm);
	},
});

frappe.ui.form.on("Weigh Bridge Bag Detail", {
	jute_bags(frm) {
		recalculate_weights(frm);
	},
	plastic_bags(frm) {
		recalculate_weights(frm);
	},
	weight_per_jute_kg(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		row.weight_per_jute_kg = trimQty(row.weight_per_jute_kg);
		recalculate_weights(frm);
	},
	weight_per_plastic_kg(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		row.weight_per_plastic_kg = trimQty(row.weight_per_plastic_kg);
		recalculate_weights(frm);
	},
});

function wbm_qc_sync_args(frm) {
	return {
		actual_truck_no: frm.doc.actual_truck_no || "",
		truck_no_in_tp: frm.doc.truck_no_in_tp || "",
		wbm_name: frm.doc.name || "",
		quality_check: frm.doc.quality_check || "",
		is_farmer_or_agent: frm.doc.is_farmer_or_agent ? 1 : 0,
		vehicle_no: frm.doc.vehicle_no || "",
	};
}

function clear_wbm_tp_fields(frm) {
	if (!frm.doc.is_farmer_or_agent) {
		frm.set_value("vehicle_no", "");
		return;
	}
	frm.set_value("pass_unique_key", "");
	frm.set_value("transit_pass_no", "");
	frm.set_value("tp_weight", 0);
	frm.set_value("pacs_name", "");
	frm.set_value("truck_no_in_tp", "");
	frm.set_value("same_truck_as_transit_pass", 0);
	frm.set_value("actual_truck_no", "");
}

function toggle_wbm_source_mode_ui(frm) {
	if (frm.doc.is_farmer_or_agent) {
		frm.remove_custom_button(__("Same as TP"), __("Truck"));
		frm.remove_custom_button(__("Different Truck"), __("Truck"));
	} else {
		setup_truck_buttons(frm);
	}
}

function setup_bag_details_grid(frm) {
	const grid = frm.fields_dict.bag_weight_details?.grid;
	if (!grid) {
		return;
	}
	if (!grid._wbm_bag_grid_ready) {
		grid._wbm_bag_grid_ready = true;
		grid.wrapper.find(".grid-add-row").hide();
	}
}

function setup_farmer_vehicle_autocomplete(frm, reload = false) {
	if (!frm.doc.is_farmer_or_agent) {
		return;
	}
	const field = frm.fields_dict.vehicle_no;
	if (!field) {
		return;
	}
	if (field.farmer_vehicle_autocomplete_setup && !reload) {
		return;
	}
	field.farmer_vehicle_autocomplete_setup = true;

	const load_options = (txt = "") => {
		frappe.call({
			method:
				"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.get_farmer_vehicle_autocomplete",
			args: { txt, limit: 25 },
			callback(r) {
				if (field.set_data) {
					field.set_data(r.message || []);
				}
			},
		});
	};

	load_options(field.get_value() || "");
	field.$input?.off("focus.farmer_vehicle");
	field.$input?.on("focus.farmer_vehicle", () => load_options(field.get_value() || ""));
	field.$input?.off("input.farmer_vehicle");
	field.$input?.on(
		"input.farmer_vehicle",
		frappe.utils.debounce(() => load_options(field.$input.val() || ""), 300)
	);
}

function setup_pass_unique_key_autocomplete(frm) {
	if (frm.doc.is_farmer_or_agent) {
		return;
	}
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

function setup_actual_truck_autocomplete(frm, reload = false) {
	const field = frm.fields_dict.actual_truck_no;
	if (!field) {
		return;
	}
	if (field.weighment_truck_autocomplete_setup && !reload) {
		return;
	}
	field.weighment_truck_autocomplete_setup = true;

	const load_options = (txt = "") => {
		frappe.call({
			method:
				"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.get_weighment_vehicle_autocomplete",
			args: { txt, limit: 25 },
			callback(r) {
				if (field.set_data) {
					field.set_data(r.message || []);
				}
			},
		});
	};

	load_options(field.get_value() || "");
	field.$input?.off("focus.weighment_truck");
	field.$input?.on("focus.weighment_truck", () => load_options(field.get_value() || ""));
	field.$input?.off("input.weighment_truck");
	field.$input?.on(
		"input.weighment_truck",
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
		["vehicle_no", "bags", "transit_pass_no", "pacs", "quantity"],
		(r) => {
			if (!r) {
				return;
			}
			frm.set_value("truck_no_in_tp", (r.vehicle_no || "").toUpperCase());
			frm.set_value("pacs_name", r.pacs || "");
			frm.set_value("tp_weight", r.quantity || 0);
			if (!frm.doc.no_of_bags && r.bags) {
				frm.set_value("no_of_bags", r.bags);
			}
			if (r.transit_pass_no) {
				frm.set_value("transit_pass_no", r.transit_pass_no);
			}
			sync_quality_from_qc(frm);
		}
	);
}

function apply_bag_details_table(frm, rows) {
	const existing = frm.doc.bag_weight_details || [];
	frm.clear_table("bag_weight_details");
	(rows || []).forEach((row, i) => {
		const prev = existing[i] || {};
		const child = frm.add_child("bag_weight_details");
		child.jute_bags = row.jute_bags || 0;
		child.plastic_bags = row.plastic_bags || 0;
		child.weight_per_jute_kg = trimQty(
			row.weight_per_jute_kg || prev.weight_per_jute_kg || 0
		);
		child.weight_per_plastic_kg = trimQty(
			row.weight_per_plastic_kg || prev.weight_per_plastic_kg || 0
		);
		child.jute_total_qt = trimQty(row.jute_total_qt || 0);
		child.plastic_total_qt = trimQty(row.plastic_total_qt || 0);
		child.gunny_weight_qt = trimQty(row.gunny_weight_qt || 0);
	});
	frm.refresh_field("bag_weight_details");
	setup_bag_details_grid(frm);
	recalculate_weights(frm);
}

function bag_table_needs_qc_sync(frm, qc, bag_details) {
	if (!qc) {
		return false;
	}
	const rows = frm.doc.bag_weight_details || [];
	if (!bag_details?.length) {
		return rows.length > 0;
	}
	if (!rows.length) {
		return true;
	}
	if (rows.length !== bag_details.length) {
		return true;
	}
	for (let i = 0; i < bag_details.length; i += 1) {
		if (
			frappe.utils.cint(rows[i].jute_bags) !== frappe.utils.cint(bag_details[i].jute_bags) ||
			frappe.utils.cint(rows[i].plastic_bags) !== frappe.utils.cint(bag_details[i].plastic_bags)
		) {
			return true;
		}
	}
	return false;
}

function should_refresh_bags_from_qc(frm, data) {
	const qc = data.quality_check || "";
	const bag_details = data.bag_details || [];
	if (!qc || !bag_details.length) {
		return false;
	}
	if (bag_table_needs_qc_sync(frm, qc, bag_details)) {
		return true;
	}
	const qc_modified = data.qc_modified || "";
	if (qc_modified && frm._wbm_qc_bag_modified !== qc_modified) {
		return true;
	}
	return false;
}

function persist_wbm_bag_details_from_qc(frm) {
	if (frm.is_new() || frm.doc.__islocal || !(frm.doc.name || "").trim()) {
		return;
	}
	frappe.call({
		method:
			"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.refresh_wbm_bag_details_from_qc",
		args: { name: frm.doc.name },
	});
}

function sync_quality_from_qc(frm) {
	if (frm._sync_quality_from_qc_pending) {
		frm._sync_quality_from_qc_queued = true;
		return;
	}
	frm._sync_quality_from_qc_pending = true;
	frm._sync_quality_from_qc_queued = false;

	frappe.call({
		method:
			"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.get_quality_check_for_wbm",
		args: wbm_qc_sync_args(frm),
		callback(r) {
			frm._sync_quality_from_qc_pending = false;
			const data = r.message || {};
			const qc = data.quality_check || "";
			const test = data.quality_test || "Pending QC";
			const slno = frappe.utils.cint(data.slno_of_qc);
			const bag_details = data.bag_details || [];
			const gate_entry = data.gate_entry || "";
			const prev_qc = frm.doc.quality_check || "";
			const prev_test = frm.doc.quality_test || "";
			const prev_slno = frappe.utils.cint(frm.doc.slno_of_qc);

			if (prev_qc !== qc) {
				frm.doc.quality_check = qc;
				frm.refresh_field("quality_check");
			}

			if ((frm.doc.gate_entry || "") !== gate_entry) {
				frm.set_value("gate_entry", gate_entry);
			}

			if (should_refresh_bags_from_qc(frm, data)) {
				apply_bag_details_table(frm, bag_details);
				frm._wbm_qc_bag_modified = data.qc_modified || "";
				persist_wbm_bag_details_from_qc(frm);
			} else if (qc && data.qc_modified) {
				frm._wbm_qc_bag_modified = data.qc_modified;
			}

			if (prev_slno !== slno) {
				frm.doc.slno_of_qc = slno;
				frm.refresh_field("slno_of_qc");
			}

			if (prev_test !== test) {
				frm.doc.quality_test = test;
				frm.refresh_field("quality_test");
			}

			if (
				!frm.is_new() &&
				!frm.doc.__islocal &&
				(prev_qc !== qc ||
					prev_test !== test ||
					prev_slno !== slno ||
					(frm.doc.gate_entry || "") !== gate_entry)
			) {
				frappe.call({
					method:
						"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.persist_quality_check_sync",
					args: {
						name: frm.doc.name,
						actual_truck_no: frm.doc.actual_truck_no || "",
						truck_no_in_tp: frm.doc.truck_no_in_tp || "",
						is_farmer_or_agent: frm.doc.is_farmer_or_agent ? 1 : 0,
						vehicle_no: frm.doc.vehicle_no || "",
					},
				});
			}

			recalculate_weights(frm);

			if (frm._sync_quality_from_qc_queued) {
				sync_quality_from_qc(frm);
			}
		},
		error() {
			frm._sync_quality_from_qc_pending = false;
			if (frm._sync_quality_from_qc_queued) {
				sync_quality_from_qc(frm);
			}
		},
	});
}

function setup_refresh_bags_from_qc_button(frm) {
	if (frm._refresh_bags_from_qc_button_setup) {
		return;
	}
	frm._refresh_bags_from_qc_button_setup = true;
	frm.add_custom_button(__("Refresh Bag Counts from QC"), () => {
		frappe.call({
			method:
				"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.get_quality_check_for_wbm",
			args: wbm_qc_sync_args(frm),
			callback(r) {
				const data = r.message || {};
				const bag_details = data.bag_details || [];
				if (!data.quality_check || !bag_details.length) {
					frappe.msgprint(__("No bag lines found on the linked Quality Check."));
					return;
				}
				apply_bag_details_table(frm, bag_details);
				frm._wbm_qc_bag_modified = data.qc_modified || "";
				persist_wbm_bag_details_from_qc(frm);
				frappe.show_alert({ message: __("Bag counts updated from Quality Check"), indicator: "green" });
			},
		});
	});
}

function setup_truck_buttons(frm) {
	if (frm.doc.is_farmer_or_agent) {
		return;
	}
	frm.remove_custom_button(__("Same as TP"), __("Truck"));
	frm.remove_custom_button(__("Different Truck"), __("Truck"));

	frm.add_custom_button(
		__("Same as TP"),
		() => {
			frm.set_value("same_truck_as_transit_pass", 0);
			frm.set_value("actual_truck_no", "");
		},
		__("Truck")
	);

	frm.add_custom_button(
		__("Different Truck"),
		() => {
			frm.set_value("same_truck_as_transit_pass", 1);
		},
		__("Truck")
	);
}

function sum_gunny_from_bag_table(frm) {
	let total_jute_qt = 0;
	let total_plastic_qt = 0;
	(frm.doc.bag_weight_details || []).forEach((row) => {
		const jute_qt = qtyFlt(
			(frappe.utils.flt(row.weight_per_jute_kg) * frappe.utils.cint(row.jute_bags)) /
				KG_PER_QUINTAL
		);
		const plastic_qt = qtyFlt(
			(frappe.utils.flt(row.weight_per_plastic_kg) * frappe.utils.cint(row.plastic_bags)) /
				KG_PER_QUINTAL
		);
		row.jute_total_qt = trimQty(jute_qt);
		row.plastic_total_qt = trimQty(plastic_qt);
		row.gunny_weight_qt = trimQty(jute_qt + plastic_qt);
		total_jute_qt += jute_qt;
		total_plastic_qt += plastic_qt;
	});
	frm.set_value("total_jute_empty_qt", qtyFlt(total_jute_qt));
	frm.set_value("total_plastic_empty_qt", qtyFlt(total_plastic_qt));

	const grid = frm.fields_dict.bag_weight_details?.grid;
	if (grid) {
		(frm.doc.bag_weight_details || []).forEach((row) => {
			const grid_row = grid.grid_rows_by_docname?.[row.name];
			if (!grid_row) {
				return;
			}
			grid_row.refresh_field("jute_total_qt");
			grid_row.refresh_field("plastic_total_qt");
			grid_row.refresh_field("gunny_weight_qt");
		});
	}

	return qtyFlt(total_jute_qt + total_plastic_qt);
}

function resolve_gunny_weight_qt(frm) {
	if (frm.doc.demo_rst_data) {
		frm.set_value("total_jute_empty_qt", 0);
		frm.set_value("total_plastic_empty_qt", 0);
		return frappe.utils.flt(frm.doc.gunny_weight);
	}
	if (frm.doc.gunny_type !== "Gunny Cut") {
		frm.set_value("total_jute_empty_qt", 0);
		frm.set_value("total_plastic_empty_qt", 0);
		return 0;
	}
	return sum_gunny_from_bag_table(frm);
}

function recalculate_weights(frm) {
	const load_weight = frappe.utils.flt(frm.doc.load_weight);
	const tare_weight = frappe.utils.flt(frm.doc.tare_weight);

	let gross_weight = 0;
	if (load_weight && tare_weight) {
		gross_weight = load_weight - tare_weight;
	} else if (load_weight) {
		gross_weight = load_weight;
	}
	frm.set_value("gross_weight", qtyFlt(gross_weight));

	const gunny_weight = resolve_gunny_weight_qt(frm);
	frm.set_value("gunny_weight", qtyFlt(gunny_weight));

	const deduction = frappe.utils.flt(frm.doc.deduction);
	const net_weight = qtyFlt(Math.max(gross_weight - gunny_weight - deduction, 0));
	frm.set_value("net_weight", net_weight);
}
