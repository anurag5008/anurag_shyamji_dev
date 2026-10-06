// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Mandi Book"] = {
	collapsible_filters: true,
	filters: [
		{
			fieldname: "season",
			label: __("Season"),
			fieldtype: "Link",
			options: "Season Master",
		},
		{
			fieldname: "mill_name",
			label: __("Mill Name (Code)"),
			fieldtype: "Link",
			options: "Mill Master",
		},
		{
			fieldname: "ppc_name",
			label: __("PPC Name"),
			fieldtype: "Link",
			options: "PPC Master",
		},
		{
			fieldname: "transit_pass_no",
			label: __("TP No"),
			fieldtype: "Data",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const fieldname = (column && (column.fieldname || column.id)) || "";
		if (data && data.pass_unique_key) {
			window.__mandi_book_rows = window.__mandi_book_rows || {};
			window.__mandi_book_rows[data.pass_unique_key] = data;
		}
		if (fieldname === "rst_count" || fieldname === "entry_count") {
			return mandi_book_open_button(fieldname, data);
		}
		if (fieldname === "chhatni_status") {
			return mandi_book_status_pill(value);
		}
		if (fieldname === "tp_status") {
			const indicator = value === __("TP Completed") ? "green" : "orange";
			return `<span class="indicator-pill ${indicator}">${frappe.utils.escape_html(value || "")}</span>`;
		}
		return default_formatter(value, row, column, data);
	},
	show_popup(kind, data) {
		mandi_book_dialog(kind, data || {});
	},
};

if (!window.__mandi_book_click_bound) {
	window.__mandi_book_click_bound = true;
	document.addEventListener(
		"click",
		(event) => {
			const start = event.target instanceof Element ? event.target : event.target && event.target.parentElement;
			const button = start && start.closest ? start.closest(".mandi-book-open") : null;
			if (!button) {
				return;
			}
			event.preventDefault();
			event.stopPropagation();
			const kind = button.getAttribute("data-kind");
			const key = decodeURIComponent(button.getAttribute("data-pass") || "");
			const row = (window.__mandi_book_rows || {})[key] || {};
			mandi_book_dialog(kind, row);
		},
		true
	);
}

function mandi_book_open_button(fieldname, data) {
	const kind = fieldname === "rst_count" ? "rst" : "entry";
	const count = cint((data && data[fieldname]) || 0);
	const label = kind === "rst" ? __("RST ({0})", [count]) : __("Entry ({0})", [count]);
	const pass_key = encodeURIComponent((data && data.pass_unique_key) || "");
	return `<button type="button" class="btn btn-xs btn-default mandi-book-open" data-kind="${kind}" data-pass="${pass_key}">${frappe.utils.escape_html(label)}</button>`;
}

function mandi_book_status_pill(value) {
	const text = value == null || value === "" ? "" : String(value);
	let indicator = "gray";
	if (text === "Chhatni Received") {
		indicator = "green";
	} else if (text === "Over Filled Chhatni Received") {
		indicator = "blue";
	} else if (text === "Chhatni Not Received") {
		indicator = "orange";
	} else if (text === "Chhatni Pending") {
		indicator = "yellow";
	}
	return `<span class="indicator-pill ${indicator}">${frappe.utils.escape_html(text)}</span>`;
}

function mandi_book_dialog(kind, data) {
	const lines = kind === "rst" ? data.rst_lines || [] : data.entry_lines || [];
	const tp_no = data.transit_pass_no || "";
	const title = kind === "rst" ? __("RST — TP {0}", [tp_no]) : __("Entry — TP {0}", [tp_no]);
	const dialog = new frappe.ui.Dialog({
		title,
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "details" }],
	});
	dialog.fields_dict.details.$wrapper.html(mandi_book_table(kind, lines));
	dialog.show();
}

function mandi_book_table(kind, lines) {
	if (kind === "rst") {
		return mandi_book_html_table(
			[
				__("RST No"),
				__("Deduction (QT)"),
				__("Weigh Bridge"),
				__("Actual Vehicle No"),
				__("Jute Pkt"),
				__("Plastic Pkt"),
				__("No. of Bags"),
				__("Total Bags"),
				__("Gunny (Gross / Cut)"),
				__("Gunny Weight (QT)"),
			],
			lines.map((line) => [
				frappe.utils.escape_html(line.rst_no || "—"),
				mandi_book_qty(line.deduction, 3),
				mandi_book_doc_link("Weigh Bridge Measurement", line.weigh_bridge_measurement),
				frappe.utils.escape_html(line.actual_vehicle_no || "—"),
				frappe.utils.escape_html(String(cint(line.jute_pkt))),
				frappe.utils.escape_html(String(cint(line.plastic_pkt))),
				frappe.utils.escape_html(String(cint(line.no_of_bags))),
				frappe.utils.escape_html(String(cint(line.total_bags))),
				frappe.utils.escape_html(line.gunny_type || "—"),
				mandi_book_qty(line.gunny_weight, 3),
			]),
			__("No RST on this TP")
		);
	}
	return mandi_book_html_table(
		[__("Entry"), __("Agent Name"), __("Quantity"), __("Price per Quintal"), __("Total Amount")],
		lines.map((line) => [
			mandi_book_doc_link("Entry", line.entry),
			frappe.utils.escape_html(line.agent_name || "—"),
			mandi_book_qty(line.entry_quantity, 3),
			mandi_book_qty(line.entry_price_per_quintal, 2),
			mandi_book_qty(line.total_amount, 2),
		]),
		__("No Entry on this TP")
	);
}

function mandi_book_html_table(headers, body, empty_text) {
	if (!body.length) {
		return `<div class="text-muted" style="padding:8px 4px;">${frappe.utils.escape_html(empty_text)}</div>`;
	}
	const head = headers.map((label) => `<th>${frappe.utils.escape_html(label)}</th>`).join("");
	const rows = body
		.map((cells) => `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
		.join("");
	return `<div style="overflow:auto;"><table class="table table-bordered table-sm" style="margin-bottom:0;"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function mandi_book_doc_link(doctype, name) {
	if (!name) {
		return "—";
	}
	const route = frappe.utils.get_form_link(doctype, name);
	return `<a href="${route}">${frappe.utils.escape_html(name)}</a>`;
}

function mandi_book_qty(value, precision) {
	const number = flt(value);
	return frappe.utils.escape_html(number.toFixed(precision));
}
