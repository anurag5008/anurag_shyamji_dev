frappe.ui.form.on("Gate Exit", {
	onload(frm) {
		setup_inside_mill_vehicle_autocomplete(frm);
	},
	refresh(frm) {
		setup_inside_mill_vehicle_autocomplete(frm);
		setup_scan_button(frm);
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
	if (!field) return;
	if (!field.gate_exit_autocomplete_ready) {
		field.gate_exit_autocomplete_ready = true;
		field.$input?.on("focus.gate_exit", () => load_inside_mill_vehicles(frm));
	}
	if (frm.is_new()) load_inside_mill_vehicles(frm);
}

// Fill the Vehicle No list with vehicles inside the mill.
function load_inside_mill_vehicles(frm) {
	const field = frm.fields_dict.vehicle_no;
	frappe.call({
		method: "ivri_od.procurement.doctype.gate_exit.gate_exit.get_inside_mill_vehicle_autocomplete",
		args: { txt: "", limit: 500 },
		callback(r) {
			const vehicles = r.message || [];
			frm.inside_mill_vehicles = vehicles.map((v) => v.value);
			field.set_data?.(vehicles);
		},
	});
}

function resolve_gate_exit(frm) {
	const vehicle = (frm.doc.vehicle_no || "").trim().toUpperCase();
	if (!vehicle) {
		frm.set_value("gate_entry_in", "");
		frm.set_value("driver_name", "");
		return;
	}
	if (frm.doc.vehicle_no !== vehicle) frm.set_value("vehicle_no", vehicle);
	if (frm.is_new() && frm.inside_mill_vehicles && !frm.inside_mill_vehicles.includes(vehicle)) {
		frm.save_after_scan = false;
		frappe.show_alert({
			message: __("Vehicle {0} is not inside the mill. Select from the list.", [vehicle]),
			indicator: "orange",
		});
		frm.set_value("vehicle_no", "");
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.gate_exit.gate_exit.resolve_gate_exit_for_vehicle",
		args: { vehicle_no: vehicle },
		callback(r) {
			const data = r.message || {};
			if (data.error) {
				frm.save_after_scan = false;
				frm.set_value("gate_entry_in", "");
				frm.set_value("driver_name", "");
				frappe.msgprint({ title: __("Gate Exit"), message: data.error, indicator: "orange" });
				return;
			}
			frm.set_value("gate_entry_in", data.gate_entry_in || "");
			frm.set_value("vehicle_no", data.vehicle_no || vehicle);
			frm.set_value("driver_name", data.driver_name || "");
			// a scanned Gate Entry QR saves the Gate Exit by itself, once, after the vehicle is found
			if (frm.save_after_scan) {
				frm.save_after_scan = false;
				frm.save();
			}
		},
	});
}

// The Gate Entry pass QR holds lines like "Vehicle No: CG04AB1234". Scanning it fills Vehicle No, and the
// normal Vehicle No handling then finds the open Gate Entry, the same as picking the vehicle from the list.
function vehicle_from_qr_text(text) {
	const match = /^\s*Vehicle No\s*:\s*(.+?)\s*$/im.exec(text || "");
	return match ? match[1].replace(/\s+/g, "").toUpperCase() : "";
}

function setup_scan_button(frm) {
	if (!frm.is_new()) return;
	frm.add_custom_button(__("Scan QR"), () => open_scan_dialog(frm));
}

function open_scan_dialog(frm) {
	let scanner = null;
	let last_alert = 0;
	// the camera reports a code on every frame, so a message is shown at most once in 3 seconds
	const warn = (message) => {
		if (Date.now() - last_alert < 3000) return;
		last_alert = Date.now();
		frappe.show_alert({ message, indicator: "orange" });
	};
	const use_scan = (text) => {
		const vehicle = vehicle_from_qr_text(text);
		const purpose = dialog.get_value("out_purpose");
		const detail = (dialog.get_value("out_purpose_detail") || "").trim();
		if (vehicle && (!purpose || (purpose === "Others" && !detail))) {
			warn(purpose ? __("Write the Purpose Details, then scan again.") : __("Select the Out Purpose, then scan again."));
			return false;
		}
		if (!vehicle) {
			warn(__("This QR code is not a Gate Entry pass. Scan the QR printed on the Gate Entry pass."));
			return false;
		}
		dialog.hide();
		frm.set_value("out_purpose", purpose);
		frm.set_value("out_purpose_detail", purpose === "Others" ? detail : "");
		frm.save_after_scan = true;
		if (frm.doc.vehicle_no === vehicle) {
			resolve_gate_exit(frm);
		} else {
			frm.set_value("vehicle_no", vehicle);
		}
		return true;
	};
	const dialog = new frappe.ui.Dialog({
		title: __("Scan Gate Entry QR"),
		fields: [
			{
				fieldtype: "Select",
				fieldname: "out_purpose",
				label: __("Out Purpose"),
				options: "\nFCI DEPO\nRRC DEPO\nOthers",
				default: frm.doc.out_purpose || "",
				reqd: 1,
				description: __("The Gate Exit is saved automatically after a successful scan."),
			},
			{
				fieldtype: "Small Text",
				fieldname: "out_purpose_detail",
				label: __("Purpose Details"),
				default: frm.doc.out_purpose_detail || "",
				depends_on: "eval:doc.out_purpose=='Others'",
				mandatory_depends_on: "eval:doc.out_purpose=='Others'",
			},
			{ fieldtype: "HTML", fieldname: "camera" },
			{
				fieldtype: "Small Text",
				fieldname: "scanned_text",
				label: __("Handheld scanner or pasted QR text"),
				description: __("Click here, then scan with a handheld scanner."),
				change() {
					const text = dialog.get_value("scanned_text");
					if (text && !use_scan(text)) dialog.set_value("scanned_text", "");
				},
			},
		],
		on_page_show() {
			if (!window.isSecureContext || !navigator.mediaDevices) {
				dialog.get_field("camera").$wrapper.html(
					`<p class="text-muted">${__("Camera scanning needs a secure (https) connection. Use a handheld scanner or paste the QR text below.")}</p>`
				);
				return;
			}
			scanner = new frappe.ui.Scanner({
				container: dialog.get_field("camera").$wrapper.addClass("barcode-scanner"),
				multiple: true,
				on_scan(result) {
					const text = result && (result.decodedText || (result.result && result.result.text));
					if (text && use_scan(text)) scanner.stop_scan();
				},
			});
			scanner.scan();
		},
		on_hide() {
			if (scanner) scanner.stop_scan();
		},
	});
	dialog.show();
}
