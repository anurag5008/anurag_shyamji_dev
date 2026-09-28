frappe.ui.form.on("Gate Exit", {
	onload(frm) {
		setup_inside_mill_vehicle_autocomplete(frm);
	},
	refresh(frm) {
		setup_inside_mill_vehicle_autocomplete(frm);
	},
	vehicle_no(frm) {
		resolve_gate_exit(frm);
	},
	out_purpose(frm) {
		if (frm.doc.out_purpose !== "Others") {
			frm.set_value("out_purpose_detail", "");
		}
	},
});

function setup_inside_mill_vehicle_autocomplete(frm) {
	const field = frm.fields_dict.vehicle_no;
	if (!field || field.gate_exit_autocomplete_ready) return;
	field.gate_exit_autocomplete_ready = true;
	const load = (txt = "") => frappe.call({
		method: "ivri_od.procurement.doctype.gate_exit.gate_exit.get_inside_mill_vehicle_autocomplete",
		args: { txt, limit: 25 },
		callback(r) { field.set_data?.(r.message || []); },
	});
	field.$input?.on("focus.gate_exit", () => load(field.get_value() || ""));
	field.$input?.on("input.gate_exit", frappe.utils.debounce(() => load(field.$input.val() || ""), 300));
}

function resolve_gate_exit(frm) {
	const vehicle = (frm.doc.vehicle_no || "").trim().toUpperCase();
	if (!vehicle) {
		frm.set_value("gate_entry_in", "");
		frm.set_value("driver_name", "");
		return;
	}
	if (frm.doc.vehicle_no !== vehicle) frm.set_value("vehicle_no", vehicle);
	frappe.call({
		method: "ivri_od.procurement.doctype.gate_exit.gate_exit.resolve_gate_exit_for_vehicle",
		args: { vehicle_no: vehicle },
		callback(r) {
			const data = r.message || {};
			if (data.error) {
				frm.set_value("gate_entry_in", "");
				frm.set_value("driver_name", "");
				frappe.msgprint({ title: __("Gate Exit"), message: data.error, indicator: "orange" });
				return;
			}
			frm.set_value("gate_entry_in", data.gate_entry_in || "");
			frm.set_value("vehicle_no", data.vehicle_no || vehicle);
			frm.set_value("driver_name", data.driver_name || "");
		},
	});
}
