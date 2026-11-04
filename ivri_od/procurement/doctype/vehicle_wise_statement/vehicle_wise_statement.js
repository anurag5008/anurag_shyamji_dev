// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// Vehicle Wise Statement: choose the Miller and Season (from the PPAS Transit Passes) and optionally a District, then "Fetch Details" lists one row
// per vehicle and PPC with the bags and the quantity of its passes added up. The user types the KM and Rate of each PPC; the Amount (Qty x Rate),
// the Voucher No of the vehicle (numbered from 1; one more voucher for every 50,000 or part of the vehicle's total) and the totals follow. Keep in step with
// ivri_od/procurement/vehicle_statement.py, which holds the same rules for the server.
const VOUCHER_LIMIT = 50000;

function vouchers_needed(amount) {
	amount = flt(amount, 2);
	if (amount <= 0) return 0;
	return Math.max(1, Math.ceil(amount / VOUCHER_LIMIT));
}

function recalculate(frm) {
	// One row for each vehicle and PPC: Amount = Qty x Rate (the KM is only noted). The S.L No and the Voucher No are for the vehicle (on its first row);
	// hired vehicles are numbered and get vouchers by their total amount; an own vehicle has no S.L No, no voucher and no payment mode (it is under an undertaking)
	const OWN = "Own Vehicle";
	const key = (row) => (row.vehicle_no || "").replace(/\s+/g, "").toUpperCase();
	const groups = [];
	(frm.doc.items || []).forEach((row) => {
		row.amount = Math.floor(flt(row.qty) * flt(row.rate) + 0.5); // to the nearest whole rupee, half a rupee goes up
		const last = groups[groups.length - 1];
		if (last && key(last[0]) === key(row)) last.push(row);
		else groups.push([row]);
	});
	let next = 1;
	let serial = 0;
	let vouchers = 0;
	const total = { hired_qty: 0, hired_amount: 0, own_qty: 0, own_amount: 0 };
	groups.forEach((group) => {
		const sum_amount = group.reduce((t, row) => t + row.amount, 0);
		const sum_qty = group.reduce((t, row) => t + flt(row.qty), 0);
		if (group[0].vehicle_type === OWN) {
			group.forEach((row) => Object.assign(row, { sl_no: "", payment_mode: "", voucher_no: "" }));
			total.own_qty += sum_qty;
			total.own_amount += sum_amount;
			return;
		}
		const count = vouchers_needed(sum_amount);
		const numbers = Array.from({ length: count }, (_, i) => next + i).join(",");
		serial += 1;
		next += count;
		vouchers += count;
		group.forEach((row, position) => {
			row.payment_mode = "CASH";
			row.sl_no = position === 0 ? String(serial) : "";
			row.voucher_no = position === 0 ? numbers : "";
		});
		total.hired_qty += sum_qty;
		total.hired_amount += sum_amount;
	});
	frm.refresh_field("items");
	frm.set_value("total_vehicles", groups.length);
	frm.set_value("hired_qty", flt(total.hired_qty, 2));
	frm.set_value("hired_amount", flt(total.hired_amount, 2));
	frm.set_value("own_qty", flt(total.own_qty, 2));
	frm.set_value("own_amount", flt(total.own_amount, 2));
	frm.set_value("total_qty", flt(total.hired_qty + total.own_qty, 2)); // G. Total
	frm.set_value("total_amount", flt(total.hired_amount + total.own_amount, 2)); // G. Total
	frm.set_value("total_vouchers", vouchers);
}

// KM and Rate belong to the PPC: what is typed on one row is also put on the other rows of the same PPC that are still empty
function copy_to_same_ppc(frm, row, field) {
	if (!row.ppc || !flt(row[field])) return;
	(frm.doc.items || []).forEach((other) => {
		if (other.name !== row.name && other.ppc === row.ppc && !flt(other[field])) other[field] = row[field];
	});
}

function set_filter_options(frm) {
	if (frm.__filter_options) return apply_options(frm, frm.__filter_options);
	frappe.call({
		method: "ivri_od.procurement.doctype.vehicle_wise_statement.vehicle_wise_statement.get_filter_options",
		callback(r) {
			frm.__filter_options = r.message || { millers: [], seasons: [] };
			apply_options(frm, frm.__filter_options);
		},
	});
}

function apply_options(frm, options) {
	frm.set_df_property("miller", "options", ["", ...options.millers].join("\n"));
	frm.set_df_property("season", "options", ["", ...options.seasons].join("\n"));
	frm.refresh_fields(["miller", "season"]);
}

// The table already has its own S.L No, so Frappe's row number column ("No.") is hidden on this table.
if (typeof document !== "undefined" && !document.getElementById("ivri-od-vws-style-v2")) {
	const style = document.createElement("style");
	style.id = "ivri-od-vws-style-v2";
	// Headers and cells of this table wrap instead of being cut with "...", so every heading and every PPC name can be read in full.
	style.textContent = [
		".ivri-no-row-number .row-index { display: none !important; }",
		".ivri-no-row-number .grid-heading-row .grid-static-col, .ivri-no-row-number .data-row .grid-static-col { height: auto !important; min-height: 32px; }",
		".ivri-no-row-number .grid-static-col .static-area, .ivri-no-row-number .grid-static-col .static-area > * { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; word-break: break-word; line-height: 1.3; }",
		".ivri-no-row-number .grid-heading-row .static-area { font-weight: 600; }",
	].join("\n");
	document.head.appendChild(style);
}

const PRINT_FORMAT = "Vehicle Wise Statement - Shyamji";
const DEBIT_VOUCHER_FORMAT = "Debit Voucher - Shyamji";

frappe.ui.form.on("Vehicle Wise Statement", {
	refresh(frm) {
		set_filter_options(frm);
		frm.fields_dict.items.grid.wrapper.addClass("ivri-no-row-number");
		const paddy = frm.doc.statement_type !== "CMR"; // only the Paddy statement is built; CMR (rice) comes later
		// Print PDF drop down (saved statements only): the statement sheet, or the debit vouchers of all its voucher numbers
		if (paddy && !frm.is_new()) {
			const download = (format, extra = {}) => {
				const query = $.param({ doctype: frm.doctype, name: frm.docname, format, no_letterhead: 1, ...extra });
				window.open(`/api/method/frappe.utils.print_format.download_pdf?${query}`);
			};
			frm.add_custom_button(__("Vehicle Statement"), () => download(PRINT_FORMAT), __("Print PDF"));
			frm.add_custom_button(__("Debit Voucher"), () => {
				// the start date goes to the first vehicles, then the next day for every next group of vehicles; all vouchers of a vehicle have one date
				frappe.prompt(
					[
						{ fieldname: "voucher_date", fieldtype: "Date", label: __("Start Date"), reqd: 1, default: frappe.datetime.get_today() },
						{ fieldname: "per_date", fieldtype: "Int", label: __("Vehicles on the same date"), reqd: 1, default: 4,
							description: __("After this many vehicles the date moves to the next day. All the vouchers of one vehicle get the same date.") },
					],
					(values) => download(DEBIT_VOUCHER_FORMAT, { voucher_date: values.voucher_date, per_date: Math.max(1, cint(values.per_date) || 4) }),
					__("Debit Voucher Dates"),
					__("Download PDF")
				);
			}, __("Print PDF"));
		}
		if (!paddy) return;
		frm.add_custom_button(__("Fetch Details"), () => {
			if (!frm.doc.miller || !frm.doc.season) return frappe.msgprint(__("Choose the Miller and the Season first."));
			frm.call({
				doc: frm.doc,
				method: "fetch_details",
				freeze: true,
				freeze_message: __("Fetching from the PPAS Transit Passes ..."),
				callback(r) {
					if (r.exc) return;
					frm.dirty();
					frm.refresh();
					frappe.show_alert({ message: __("{0} vehicles fetched.", [r.message]), indicator: "green" });
				},
			});
		}).addClass("btn-primary");
	},
	season(frm) {
		frm.set_value("kms_title", "");
	},
	statement_type(frm) {
		frm.trigger("refresh");
	},
});

frappe.ui.form.on("Vehicle Wise Statement Item", {
	km(frm, cdt, cdn) {
		copy_to_same_ppc(frm, locals[cdt][cdn], "km");
		recalculate(frm);
	},
	rate(frm, cdt, cdn) {
		copy_to_same_ppc(frm, locals[cdt][cdn], "rate");
		recalculate(frm);
	},
	items_remove(frm) {
		recalculate(frm);
	},
});
