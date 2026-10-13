// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

const QC_CHILD_TABLE_CONFIG = [
	{
		fieldname: "old_new_bags",
		label: __("Paddy Type (In Bags)"),
		hint: __("Old Paddy Bags / New Paddy Bags"),
		is_filled: is_old_new_bag_row_filled,
	},
	{
		fieldname: "type_of_pkt",
		label: __("Type of Bags"),
		hint: __("Jute Bag No / No of Plastic Bag"),
		is_filled: is_type_of_pkt_row_filled,
	},
];

const QC_CHILD_TABLES = QC_CHILD_TABLE_CONFIG.map((cfg) => cfg.fieldname);

frappe.ui.form.on("Quality Check", {
	onload(frm) {
		setup_vehicle_no_autocomplete(frm);
		setup_qc_child_table_grids(frm);
	},
	refresh(frm) {
		setup_vehicle_no_autocomplete(frm);
		sync_qc_decision_from_returns(frm);
		setup_qc_child_table_grids(frm);
	},
	validate(frm) {
		validate_qc_child_tables_single_row(frm);
	},
	vehicle_no(frm) {
		debounced_resolve_gate_entry(frm);
	},
	paddy_returned(frm) {
		sync_qc_decision_from_returns(frm);
	},
	is_farmer_or_agent(frm) {
		clear_qc_source_mode_fields(frm);
	},
	farmer_name(frm) {
		if (frm.doc.farmer_name) {
			frm.set_value("farmer_name", frm.doc.farmer_name.trim());
		}
	},
	old_new_bags(frm) {
		qc_child_table_changed(frm, "old_new_bags");
	},
	old_new_bags_add(frm) {
		qc_child_table_changed(frm, "old_new_bags");
	},
	old_new_bags_remove(frm) {
		qc_child_table_changed(frm, "old_new_bags");
	},
	type_of_pkt(frm) {
		qc_child_table_changed(frm, "type_of_pkt");
	},
	type_of_pkt_add(frm) {
		qc_child_table_changed(frm, "type_of_pkt");
	},
	type_of_pkt_remove(frm) {
		qc_child_table_changed(frm, "type_of_pkt");
	},
});

function is_old_new_bag_row_filled(row) {
	return frappe.utils.cint(row.old_bags) > 0 || frappe.utils.cint(row.new_bags) > 0;
}

function is_type_of_pkt_row_filled(row) {
	return (
		frappe.utils.cint(row.jute_pkt_no) > 0 ||
		frappe.utils.cint(row.no_of_plastic_bag) > 0
	);
}

function validate_qc_child_tables_single_row(frm) {
	for (const { fieldname, label, hint, is_filled } of QC_CHILD_TABLE_CONFIG) {
		const rows = frm.doc[fieldname] || [];
		const filled = rows.filter((row) => is_filled(row));

		if (filled.length > 1) {
			frappe.throw(
				__("Only one row can be filled in {0}. Remove extra rows with data.", [label])
			);
		}
		if (rows.length > 1) {
			frappe.throw(
				__("Only one row is allowed in {0}. Delete extra rows before saving.", [label])
			);
		}
		if (!filled.length) {
			frappe.throw(__("Enter one row in {0} ({1}).", [label, hint]));
		}
	}
}

function qc_child_table_changed(frm, fieldname) {
	enforce_single_qc_grid_row(frm, fieldname);
	sync_qc_child_table_limits(frm);
}

function setup_qc_child_table_grids(frm) {
	const apply = () => {
		QC_CHILD_TABLES.forEach((fieldname) => {
			bind_qc_single_row_grid(frm, fieldname);
			sync_qc_child_table_limits(frm, fieldname);
		});
	};
	apply();
	setTimeout(apply, 0);
}

function bind_qc_single_row_grid(frm, fieldname) {
	const grid = frm.fields_dict[fieldname]?.grid;
	if (!grid) {
		return;
	}

	if (!grid._qc_orig_add_new_row) {
		grid._qc_orig_add_new_row = grid.add_new_row.bind(grid);
	}

	grid.add_new_row = function (...args) {
		if ((frm.doc[fieldname] || []).length >= 1) {
			sync_qc_child_table_limits(frm, fieldname);
			return;
		}
		return grid._qc_orig_add_new_row(...args);
	};

	grid.wrapper.off("click.qc-single-row");
	grid.wrapper.on("click.qc-single-row", ".grid-add-row", (e) => {
		if ((frm.doc[fieldname] || []).length >= 1) {
			e.preventDefault();
			e.stopImmediatePropagation();
			sync_qc_child_table_limits(frm, fieldname);
			return false;
		}
	});
}

function enforce_single_qc_grid_row(frm, fieldname) {
	const rows = frm.doc[fieldname] || [];
	if (rows.length <= 1) {
		return;
	}
	while (frm.doc[fieldname].length > 1) {
		const last = frm.doc[fieldname][frm.doc[fieldname].length - 1];
		frappe.model.remove_child(frm.doc, fieldname, last.name);
	}
	frm.refresh_field(fieldname);
}

function sync_qc_child_table_limits(frm, fieldname) {
	const tables = fieldname ? [fieldname] : QC_CHILD_TABLES;
	tables.forEach((table_fieldname) => {
		const row_count = (frm.doc[table_fieldname] || []).length;
		const at_limit = row_count >= 1;

		frm.set_df_property(table_fieldname, "cannot_add_rows", at_limit ? 1 : 0);

		const grid = frm.fields_dict[table_fieldname]?.grid;
		if (!grid) {
			return;
		}

		grid.cannot_add_rows = at_limit;
		if (grid.df) {
			grid.df.cannot_add_rows = at_limit ? 1 : 0;
		}

		if (typeof grid.setup_toolbar === "function") {
			grid.setup_toolbar();
		}

		grid.wrapper
			.find(".grid-add-row, .grid-add-multiple-rows, .grid-duplicate-rows")
			.toggleClass("hidden", at_limit)
			.prop("disabled", at_limit);
	});
}

function clear_qc_source_mode_fields(frm) {
	if (frm.doc.is_farmer_or_agent) {
		frm.set_value("unloading_point", "");
		frm.set_value("staff_name", "");
	} else {
		frm.set_value("farmer_name", "");
	}
}

function sync_qc_decision_from_returns(frm) {
	const returned = frappe.utils.cint(frm.doc.paddy_returned);
	const decision = returned <= 0 ? "Accepted" : "Partially Accepted";
	if ((frm.doc.qc_decision || "") !== decision) {
		frm.set_value("qc_decision", decision);
	}
}

const debounced_resolve_gate_entry = frappe.utils.debounce((frm) => {
	resolve_gate_entry_from_vehicle(frm);
}, 400);

function setup_vehicle_no_autocomplete(frm) {
	const field = frm.fields_dict.vehicle_no;
	if (!field || field.vehicle_no_autocomplete_setup) {
		return;
	}
	field.vehicle_no_autocomplete_setup = true;

	const load_options = (txt = "") => {
		frappe.call({
			method:
				"ivri_od.procurement.doctype.quality_check.quality_check.get_vehicle_no_autocomplete",
			args: {
				txt,
				limit: 25,
				exclude_qc: get_exclude_qc(frm),
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

function get_exclude_qc(frm) {
	if (frm.is_new() || frm.doc.__islocal) {
		return "";
	}
	return frm.doc.name || "";
}

function resolve_gate_entry_from_vehicle(frm) {
	const vehicle = (frm.doc.vehicle_no || "").trim().toUpperCase();
	if (!vehicle) {
		frm.set_value("gate_entry", "");
		frm.set_value("driver_name", "");
		return;
	}

	if (frm.doc.vehicle_no !== vehicle) {
		frm.set_value("vehicle_no", vehicle);
	}

	frappe.call({
		method:
			"ivri_od.procurement.doctype.quality_check.quality_check.resolve_gate_entry_for_vehicle",
		args: {
			vehicle_no: vehicle,
			exclude_qc: get_exclude_qc(frm),
		},
		callback(r) {
			const data = r.message || {};
			if (data.error) {
				frm.set_value("gate_entry", "");
				frm.set_value("driver_name", "");
				if (vehicle.length >= 4) {
					frappe.msgprint({
						title: __("Vehicle No"),
						message: data.error,
						indicator: "orange",
					});
				}
				return;
			}
			if (data.vehicle_no) {
				frm.set_value("vehicle_no", data.vehicle_no);
			}
			frm.set_value("gate_entry", data.gate_entry || "");
			frm.set_value("driver_name", data.driver_name || "");
		},
	});
}
