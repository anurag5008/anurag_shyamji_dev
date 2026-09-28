// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Quality Check", {
	onload(frm) {
		setup_vehicle_no_autocomplete(frm);
	},
	refresh(frm) {
		setup_vehicle_no_autocomplete(frm);
		setup_quality_test_buttons(frm);
	},
	vehicle_no(frm) {
		debounced_resolve_gate_entry(frm);
	},
	qc_decision(frm) {
		sync_qc_decision_fields(frm);
	},
	is_farmer_or_agent(frm) {
		clear_qc_source_mode_fields(frm);
	},
	farmer_name(frm) {
		if (frm.doc.farmer_name) {
			frm.set_value("farmer_name", frm.doc.farmer_name.trim());
		}
	},
});

function clear_qc_source_mode_fields(frm) {
	if (frm.doc.is_farmer_or_agent) {
		frm.set_value("party_name", "");
		frm.set_value("society_name", "");
		frm.set_value("unloading_point", "");
		frm.set_value("staff_name", "");
	} else {
		frm.set_value("farmer_name", "");
	}
}

const debounced_resolve_gate_entry = frappe.utils.debounce((frm) => {
	resolve_gate_entry_from_vehicle(frm);
}, 400);

function setup_quality_test_buttons(frm) {
	const group = __("Quality Test");
	frm.remove_custom_button(__("Accepted"), group);
	frm.remove_custom_button(__("Partially Accepted"), group);
	frm.remove_custom_button(__("Rejected"), group);

	frm.add_custom_button(
		__("Accepted"),
		() => {
			frm.set_value("qc_decision", "Accepted");
		},
		group
	);
	frm.add_custom_button(
		__("Partially Accepted"),
		() => {
			frm.set_value("qc_decision", "Partially Accepted");
		},
		group
	);
	frm.add_custom_button(
		__("Rejected"),
		() => {
			frm.set_value("qc_decision", "Rejected");
		},
		group
	);
}

function sync_qc_decision_fields(frm) {
	// Reserved for future field dependencies on Quality Test.
}

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
