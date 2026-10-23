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
	setup(frm) {
		setup_qc_child_table_grids(frm);
	},
	onload(frm) {
		setup_vehicle_no_autocomplete(frm);
		setup_qc_child_table_grids(frm);
	},
	refresh(frm) {
		frm.toggle_display("is_farmer_or_agent", Boolean(frm.doc.is_farmer_or_agent));
		setup_vehicle_no_autocomplete(frm);
		sync_qc_decision_from_returns(frm);
		setup_qc_child_table_grids(frm);
	},
	onload_post_render(frm) {
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
	old_new_bags_add(frm, cdt, cdn) {
		if ((frm.doc.old_new_bags || []).length > 1 && cdn) {
			frappe.model.remove_child(frm.doc, "old_new_bags", cdn);
			frm.refresh_field("old_new_bags");
		}
		setup_qc_child_table_grids(frm);
	},
	old_new_bags_remove(frm) {
		ensure_single_qc_grid_row(frm, "old_new_bags");
		setup_qc_child_table_grids(frm);
	},
	type_of_pkt_add(frm, cdt, cdn) {
		if ((frm.doc.type_of_pkt || []).length > 1 && cdn) {
			frappe.model.remove_child(frm.doc, "type_of_pkt", cdn);
			frm.refresh_field("type_of_pkt");
		}
		setup_qc_child_table_grids(frm);
	},
	type_of_pkt_remove(frm) {
		ensure_single_qc_grid_row(frm, "type_of_pkt");
		setup_qc_child_table_grids(frm);
	},
});

function is_old_new_bag_row_filled(row) {
	return cint(row.old_bags) > 0 || cint(row.new_bags) > 0;
}

function is_type_of_pkt_row_filled(row) {
	return (
		cint(row.jute_pkt_no) > 0 ||
		cint(row.no_of_plastic_bag) > 0
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

function setup_qc_child_table_grids(frm) {
	QC_CHILD_TABLES.forEach((fieldname) => {
		frm.set_df_property(fieldname, "cannot_add_rows", true);
		frm.set_df_property(fieldname, "cannot_delete_rows", true);

		const meta_df = frappe.meta.get_docfield(frm.doctype, fieldname, frm.docname);
		if (meta_df) {
			meta_df.cannot_add_rows = true;
			meta_df.cannot_delete_rows = true;
		}

		ensure_single_qc_grid_row(frm, fieldname);

		const field = frm.get_field(fieldname);
		const grid = field?.grid;
		if (!grid) {
			return;
		}

		Object.defineProperty(grid, "cannot_add_rows", {
			get() {
				return true;
			},
			set() {},
			configurable: true,
		});
		Object.defineProperty(grid, "cannot_delete_rows", {
			get() {
				return true;
			},
			set() {},
			configurable: true,
		});

		if (grid.df) {
			grid.df.cannot_add_rows = true;
			grid.df.cannot_delete_rows = true;
		}

		grid.add_new_row = function () {
			return false;
		};

		if (!grid._qc_toolbar_patched) {
			grid._qc_toolbar_patched = true;
			const orig_setup_toolbar = grid.setup_toolbar.bind(grid);
			grid.setup_toolbar = function () {
				orig_setup_toolbar();
				this.wrapper
					.find(".grid-add-row, .grid-add-multiple-rows, .grid-duplicate-rows")
					.addClass("hidden")
					.hide();
			};
		}

		grid.setup_toolbar();
	});
}

function ensure_single_qc_grid_row(frm, fieldname) {
	const rows = frm.doc[fieldname] || [];
	if (rows.length === 0) {
		frm.add_child(fieldname);
		frm.refresh_field(fieldname);
	}
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
	const returned = cint(frm.doc.paddy_returned);
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
