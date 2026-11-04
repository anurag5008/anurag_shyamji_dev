// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// Rice mill fields on the Purchase Order. The fields show or hide from their own "depends on" rules;
// this script lists only Transporters, limits the Company dropdown to the legal Companies (not the Raw / Boiled
// variants; see ivri_od/procurement/legal_companies.py) and shows Total Hamali (bags x Hamali Rate) while the user types.
// The bags are the quantity of the Items rows whose UOM is Bags (or Nos, on older orders). The UOM of an Item row can only be Bags, Trip or Quintal.
const DEFAULT_COMPANY = "Laddu Gopal Industries";
const DEFAULT_HAMALI_RATE = 3;
const ALLOWED_UOMS = ["Bags", "Trip", "Quintal"];
const TRIP_UOM = "Trip";
const QUINTAL_PER_MT = 10; // the Avg Wt is entered in MT but the Rate is per quintal; keep in step with QUINTAL_PER_MT in purchase_order_mill.py
const DEFAULT_AVG_WT = 25; // keep in step with the default of the Avg Wt field and DEFAULT_AVG_WT in purchase_order_mill.py
const LOT_DELIVERY_AVG_WT = 29; // the Avg Wt a Trip row starts with when its Quality is a Lot Delivery one

// Quality and Dimension choices of an Items row by Item Code (strict JSON; keep in step with ITEM_RULES in purchase_order_mill.py
// and the "depends on" of the two Purchase Order Item fields, which hide a field for an Item without choices).
// The fields hold every choice, so a saved value stays valid; the choices shown to the user are narrowed here, row by row.
const ITEM_RULES = {
	"BOILED-RICE": {
		"quality": [
			"Fresh Milling",
			"Lot Delivery",
			"PDS"
		],
		"dimension": []
	},
	"BIOMASS-PELLET": {
		"quality": [
			"Rice Husk",
			"Saw Dust",
			"Mix"
		],
		"dimension": [
			"8mm",
			"10mm",
			"16mm"
		]
	},
	"BIOMASS-BRIQUETTE": {
		"quality": [
			"Rice Husk",
			"Saw Dust",
			"Mix"
		],
		"dimension": [
			"90mm"
		]
	},
	"RAW-RICE": {
		"quality": [
			"25% Broken Fresh Milling",
			"10% Broken Fresh Milling",
			"25% Broken Lot Delivery",
			"10% Broken Lot Delivery",
			"25% Broken PDS",
			"10% Broken PDS"
		],
		"dimension": []
	},
	"RICE-BRAN": {
		"quality": [
			"Boiled",
			"Raw",
			"Muri",
			"Silky"
		],
		"dimension": []
	},
	"REJECTION": {
		"quality": [
			"Boiled",
			"Raw",
			"Muri"
		],
		"dimension": []
	},
	"HUSK": {
		"quality": [],
		"dimension": []
	},
	"ASH": {
		"quality": [],
		"dimension": []
	}
};
const DEFAULT_DIMENSION = { "BIOMASS-BRIQUETTE": "90mm" };
const ROW_FIELDS = ["quality", "dimension"];
const DUST_ITEM = "PADDY";
const HAMALI_UOMS = ["Bags", "Nos"]; // Nos is kept for orders made before Bags was added
const PDS_QUALITY = "PDS";

// The Gunny field is shown only while an Items row is Boiled Rice, Raw Rice, Muri Rice or Paddy (keep in step with GUNNY_ITEMS in purchase_order_mill.py),
// and is hidden while an Items row has the UOM Trip; an old answer is cleared when it is hidden.
const GUNNY_ITEMS = ["BOILED-RICE", "RAW-RICE", "MURI-RICE", "PADDY"];
function update_gunny_field(frm) {
	const rows = frm.doc.items || [];
	const show = rows.some((row) => GUNNY_ITEMS.includes(row.item_code)) && !rows.some((row) => row.uom === TRIP_UOM);
	frm.toggle_display("gunny_condition", show);
	if (!show && frm.doc.gunny_condition) frm.set_value("gunny_condition", "");
}

// The Hamali section shows only while an Items row has the UOM Bags; without one an old Hamali answer is cleared.
function update_hamali_section(frm) {
	const has_bags = (frm.doc.items || []).some((row) => HAMALI_UOMS.includes(row.uom));
	frm.toggle_display("hamali_section", has_bags);
	if (has_bags) return;
	if (frm.doc.hamali_payer) frm.set_value("hamali_payer", "");
	if (flt(frm.doc.hamali_rate)) frm.set_value("hamali_rate", 0);
	if (flt(frm.doc.total_hamali)) frm.set_value("total_hamali", 0);
}
const PDS_RATE_FIELDS = ["quality_pds_rate_1", "quality_pds_rate_2", "quality_pds_rate_3"];

// The three Quality PDS Rate fields (below the Items table) show only while a row's Quality is PDS (also 25% / 10% Broken PDS);
// without a PDS row an old rate is cleared.
function update_pds_rates(frm) {
	const has_pds = (frm.doc.items || []).some((row) => (row.quality || "").includes(PDS_QUALITY));
	PDS_RATE_FIELDS.forEach((field) => {
		frm.toggle_display(field, has_pds);
		if (!has_pds && flt(frm.doc[field])) frm.set_value(field, 0);
	});
}

// The Dust field shows only while an Item row is Paddy; without Paddy an old answer is cleared.
function update_dust_field(frm) {
	const has_paddy = (frm.doc.items || []).some((row) => row.item_code === DUST_ITEM);
	frm.toggle_display("dust_condition", has_paddy);
	if (!has_paddy && frm.doc.dust_condition) frm.set_value("dust_condition", "");
}

const BRAN_COLUMNS = ["rate_per_mt", "oil_percentage"]; // the Rice Bran columns of the Items table
const BRAN_ITEM = "RICE-BRAN";
const BRAN_OIL_DEFAULT = { Boiled: 25, Muri: 25, Raw: 22 }; // the benchmark Oil Percentage a Rice Bran row starts with; keep in step with BRAN_OIL_DEFAULT in purchase_order_mill.py
const BRAN_UOMS = ["Quintal", "Trip"]; // Rate Per MT works with these UOMs (1 MT is 10 quintal)

function is_bran(row) {
	return !!row && row.item_code === BRAN_ITEM;
}

// A Rice Bran row starts with the benchmark Oil Percentage of its Quality (Boiled, Muri 25; Raw 22). The user can change it:
// only an empty value or one of the defaults is replaced, so a typed value stays.
function set_bran_defaults(cdt, cdn) {
	const row = cdt && locals[cdt] && locals[cdt][cdn];
	if (!is_bran(row)) return;
	const wanted = BRAN_OIL_DEFAULT[row.quality] || 0;
	const current = flt(row.oil_percentage);
	if ((!current || Object.values(BRAN_OIL_DEFAULT).includes(current)) && current !== wanted) {
		frappe.model.set_value(cdt, cdn, "oil_percentage", wanted);
	}
}

// Rate (per quintal) = Rate Per MT / 10; with the Actual Oil Percentage Received: (Rate Per MT / Benchmark Oil %) x Actual Oil % / 10.
// The quoted Rate Per MT itself is never changed.
function bran_rate(row) {
	let per_mt = flt(row.rate_per_mt);
	if (flt(row.oil_percentage) && flt(row.actual_oil_percentage)) per_mt = (per_mt * flt(row.actual_oil_percentage)) / flt(row.oil_percentage);
	return per_mt / QUINTAL_PER_MT;
}

function set_bran_rate(cdt, cdn) {
	const row = cdt && locals[cdt] && locals[cdt][cdn];
	if (!is_bran(row) || !flt(row.rate_per_mt) || !BRAN_UOMS.includes(row.uom)) return;
	const rate = flt(bran_rate(row), precision("rate", row));
	if (flt(row.rate) !== rate) frappe.model.set_value(cdt, cdn, "rate", rate);
}

// The Quality and Dimension columns of the Items table show only while a row's Item has such choices
// (a row of an Item without them stays empty inside a shown column, and the fields stay hidden in that row's form).
// The Avg Wt column shows only while a row's UOM is Trip.
function update_item_columns(frm) {
	const grid = frm.fields_dict && frm.fields_dict.items && frm.fields_dict.items.grid;
	if (!grid || !grid.set_column_disp_in_list_view) return;
	const wanted = ROW_FIELDS.filter((field) =>
		(frm.doc.items || []).some((row) => ((ITEM_RULES[row.item_code] || {})[field] || []).length)
	);
	if ((frm.doc.items || []).some((row) => row.uom === TRIP_UOM)) wanted.push("avg_wt");
	if ((frm.doc.items || []).some(is_bran)) wanted.push(...BRAN_COLUMNS);
	// the Rate is not asked for Rice Bran (it follows Rate Per MT): its column goes only when every Item row is Rice Bran
	const rows_with_item = (frm.doc.items || []).filter((row) => row.item_code);
	if (!(rows_with_item.length && rows_with_item.every(is_bran))) wanted.push("rate");
	const key = wanted.join(",");
	if (frm.__item_columns === key) return;
	frm.__item_columns = key;
	grid.set_column_disp_in_list_view([...ROW_FIELDS, "avg_wt", ...BRAN_COLUMNS, "rate"].filter((f) => !wanted.includes(f)), false);
	grid.set_column_disp_in_list_view(wanted, true);
}

// Set the choices of one row. `item_changed` also clears a choice the new Item does not have and fills the default Dimension.
function apply_item_rules(frm, cdt, cdn, item_changed) {
	const row = locals[cdt] && locals[cdt][cdn];
	if (!row) return;
	const rule = ITEM_RULES[row.item_code] || {};
	ROW_FIELDS.forEach((field) => {
		const choices = rule[field] || [];
		const df = frappe.meta.get_docfield(cdt, field, cdn);
		if (df) df.options = ["", ...choices].join("\n");
		if (!item_changed) return;
		if (row[field] && !choices.includes(row[field])) {
			frappe.model.set_value(cdt, cdn, field, "");
		}
		if (field === "dimension" && !row.dimension && DEFAULT_DIMENSION[row.item_code]) {
			frappe.model.set_value(cdt, cdn, field, DEFAULT_DIMENSION[row.item_code]);
		}
	});
	const grid_row = frm.fields_dict.items && frm.fields_dict.items.grid.grid_rows_by_docname[cdn];
	if (grid_row) grid_row.refresh();
	update_item_columns(frm);
}

// ERPNext shows an Item in the Items table as "CODE: Name" and compares the two exactly, so "HUSK" and "Husk" were shown twice ("HUSK: Husk").
// When the name is the code written another way (capitals, spaces, dashes), only the code is shown. Other Items keep "CODE: Name".
function same_words(a, b) {
	const plain = (text) => (text || "").toLowerCase().replace(/[^a-z0-9]/g, "");
	return !!plain(a) && plain(a) === plain(b);
}

if (typeof frappe !== "undefined" && frappe.form && frappe.form.link_formatters && !frappe.form.__ivri_od_item_title) {
	frappe.form.__ivri_od_item_title = true;
	const item_title = frappe.form.link_formatters["Item"];
	frappe.form.link_formatters["Item"] = function (value, doc, df) {
		if (doc && doc.doctype === "Purchase Order Item" && same_words(value, doc.item_name)) return value;
		return item_title ? item_title.apply(this, arguments) : value;
	};
}

// The Items table header: a long heading wraps onto a second line instead of being cut ("Quantit...", "Dimen..."), and a long Item
// (BIOMASS-BRIQUETTE) wraps in its cell instead of being cut,
// and the headings use less side space so "Quantity" and "Dimension(mm)" fit their columns.
if (typeof document !== "undefined" && !document.getElementById("ivri-od-po-items-header")) {
	const style = document.createElement("style");
	style.id = "ivri-od-po-items-header";
	style.textContent = `
		/* Items table: every heading and every cell wraps onto more lines instead of being cut ("Quantit...", "25% Broken Fresh Mil..."), so the whole table can be read at a glance */
		[data-fieldname="items"] .grid-heading-row, [data-fieldname="items"] .grid-heading-row .data-row { height: auto !important; min-height: 32px; }
		[data-fieldname="items"] .grid-heading-row .col { padding: 6px 4px; height: auto !important; }
		[data-fieldname="items"] .grid-heading-row .static-area, [data-fieldname="items"] .grid-heading-row .static-area.ellipsis { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; line-height: 1.2; word-break: break-word; }
		[data-fieldname="items"] .grid-body .grid-row .data-row { height: auto !important; min-height: 40px; }
		[data-fieldname="items"] .grid-body .grid-row .data-row .col { height: auto !important; align-items: flex-start; }
		[data-fieldname="items"] .grid-body .grid-row .data-row .col .static-area,
		[data-fieldname="items"] .grid-body .grid-row .data-row .col .static-area.ellipsis,
		[data-fieldname="items"] .grid-body .grid-row .data-row .col .static-area a,
		[data-fieldname="items"] .grid-body .grid-row .data-row .col .static-area span { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; line-height: 1.25; word-break: break-word; }`;
	document.head.appendChild(style);
}

// Second safeguard: whenever a Quality or Dimension dropdown of an Items row is opened, its choices are checked against the row's Item
// again, so a dropdown that was built before the Item was chosen (or from the full list of choices) cannot show another Item's choices.
function narrow_select(select) {
	const field = select.getAttribute("data-fieldname");
	const grid_row = $(select).closest(".grid-row").data("grid_row");
	const doc = grid_row && grid_row.doc;
	if (!doc || doc.doctype !== "Purchase Order Item" || !ROW_FIELDS.includes(field)) return;
	const choices = ["", ...(((ITEM_RULES[doc.item_code] || {})[field]) || [])];
	if ([...select.options].map((o) => o.value).join("\n") === choices.join("\n")) return;
	const value = select.value;
	select.innerHTML = choices
		.map((c) => `<option value="${frappe.utils.escape_html(c)}">${frappe.utils.escape_html(c)}</option>`)
		.join("");
	select.value = choices.includes(value) ? value : "";
}

if (typeof $ !== "undefined" && !window.__ivri_od_narrow_selects) {
	window.__ivri_od_narrow_selects = true;
	$(document).on(
		"mousedown focusin",
		".grid-row select[data-fieldname='quality'], .grid-row select[data-fieldname='dimension']",
		function () {
			narrow_select(this);
		}
	);
}

// ERPNext sets its own UOM dropdown for the Items rows (all UOMs of the Item) after this form's setup,
// so the limit is set again on every refresh, which runs after it.
function limit_item_uoms(frm) {
	frm.set_query("uom", "items", () => ({ filters: { name: ["in", ALLOWED_UOMS] } }));
}

// ERPNext shows Net Total (and its Company Currency copy) again whenever a discount is set, whatever the Property Setter says.
// These totals stay hidden: every toggle_display call for them is turned into "hide".
const ALWAYS_HIDDEN_TOTALS = ["net_total", "base_net_total", "base_total"];
function keep_totals_hidden(frm) {
	if (frm.__po_totals_hidden) return;
	frm.__po_totals_hidden = true;
	const toggle_display = frm.toggle_display.bind(frm);
	frm.toggle_display = function (fieldnames, show) {
		const names = Array.isArray(fieldnames) ? fieldnames : [fieldnames];
		const hide = names.filter((name) => ALWAYS_HIDDEN_TOTALS.includes(name));
		const rest = names.filter((name) => !ALWAYS_HIDDEN_TOTALS.includes(name));
		if (hide.length) toggle_display(hide, false);
		return rest.length ? toggle_display(rest, show) : undefined;
	};
	toggle_display(ALWAYS_HIDDEN_TOTALS, false);
}

// ERPNext cannot fetch an Item's details (Item Name, rate, UOM) without a Company, and the form does not require one.
// So an empty Company is filled with the default before an Item row is picked.
function ensure_company(frm) {
	if (!frm.doc.company) frm.set_value("company", DEFAULT_COMPANY);
}

frappe.ui.form.on("Purchase Order", {
	company(frm) {
		// clearing the prefilled Company means "do not print the name": the Company itself is put back (ERPNext needs it), the print flag is unticked
		if (!frm.doc.company) {
			frm.set_value("print_company_name", 0);
			ensure_company(frm);
			frappe.show_alert({ message: __("Company name will not be printed on this Purchase Order."), indicator: "orange" });
			return;
		}
		// the Cost Center (and each row's) belongs to the old Company: take the new Company's default
		frappe.db.get_value("Company", frm.doc.company, "cost_center").then((r) => {
			const center = (r.message || {}).cost_center;
			if (!center) return;
			frm.set_value("cost_center", center);
			(frm.doc.items || []).forEach((row) => frappe.model.set_value(row.doctype, row.name, "cost_center", center));
		});
	},
	setup(frm) {
		keep_totals_hidden(frm);
		follow_erpnext_total(frm);
		limit_item_uoms(frm);
		frm.set_query("transporter", () => ({ filters: { is_transporter: 1 } }));
		frm.set_query("company", () => ({
			query: "ivri_od.procurement.legal_companies.legal_company_query",
		}));
	},
	refresh(frm) {
		keep_totals_hidden(frm);
		follow_erpnext_total(frm);
		limit_item_uoms(frm);
		(frm.doc.items || []).forEach((row) => apply_item_rules(frm, row.doctype, row.name, false));
		update_item_columns(frm);
		update_dust_field(frm);
		update_pds_rates(frm);
		update_hamali_section(frm);
		update_gunny_field(frm);
		set_total_final_amount(frm);
		add_print_pdf_button(frm);
	},
	onload(frm) {
		// a fresh Purchase Order starts with Laddu Gopal Industries; one made from another document (it already has Items) keeps its Company
		if (frm.is_new() && !(frm.doc.items || []).some((row) => row.item_code)) {
			frm.set_value("company", DEFAULT_COMPANY);
		}
	},
	hamali_rate(frm) {
		set_total_hamali(frm);
	},
	payment_mode(frm) {
		// the Additional Discount section is shown only for Cash (its own "depends on"); another mode clears an old discount
		if (frm.doc.payment_mode !== "Cash" && (flt(frm.doc.discount_amount) || flt(frm.doc.additional_discount_percentage))) {
			frm.set_value("additional_discount_percentage", 0);
			frm.set_value("discount_amount", 0);
		}
	},
	hamali_payer(frm) {
		// Yes shows the Hamali Rate and Total (the rate starts at the usual 3); No clears them
		if (frm.doc.hamali_payer === "Yes") {
			if (!flt(frm.doc.hamali_rate)) frm.set_value("hamali_rate", DEFAULT_HAMALI_RATE);
		} else {
			frm.set_value("hamali_rate", 0);
		}
		set_total_hamali(frm);
	},
	delivery_type(frm) {
		if (frm.doc.delivery_type !== "X-location") {
			frm.set_value("location_name", "");
		}
	},
	vehicle_ownership(frm) {
		if (frm.doc.vehicle_ownership !== "Transport Vehicle") {
			["transporter", "vehicle_number", "driver"].forEach((field) => frm.set_value(field, ""));
			frm.set_value("freight_charges", 0);
		}
	},
});

frappe.ui.form.on("Purchase Order Item", {
	item_code(frm, cdt, cdn) {
		ensure_company(frm);
		set_bran_defaults(cdt, cdn);
		apply_item_rules(frm, cdt, cdn, true);
		update_dust_field(frm);
		update_gunny_field(frm);
	},
	form_render(frm, cdt, cdn) {
		apply_item_rules(frm, cdt, cdn, false);
	},
	items_add(frm, cdt, cdn) {
		ensure_company(frm);
		apply_item_rules(frm, cdt, cdn, false);
	},
	qty(frm) {
		set_total_hamali(frm);
	},
	quality(frm, cdt, cdn) {
		set_default_avg_wt(cdt, cdn);
		set_bran_defaults(cdt, cdn);
		update_pds_rates(frm);
	},
	uom(frm, cdt, cdn) {
		set_default_avg_wt(cdt, cdn);
		set_bran_rate(cdt, cdn);
		update_item_columns(frm);
		update_hamali_section(frm);
		update_gunny_field(frm);
		recalculate(frm);
		set_total_hamali(frm);
	},
	rate_per_mt(frm, cdt, cdn) {
		set_bran_rate(cdt, cdn);
		recalculate(frm);
	},
	avg_wt(frm) {
		recalculate(frm);
	},
	items_remove(frm) {
		update_item_columns(frm);
		update_dust_field(frm);
		update_pds_rates(frm);
		update_hamali_section(frm);
		update_gunny_field(frm);
		recalculate(frm);
		set_total_hamali(frm);
	},
});

// A visible Print PDF button: it downloads the Shyamji Purchase Order format without a letterhead (the format has its own header).
const PRINT_FORMAT = "Purchase Order - Shyamji";
function add_print_pdf_button(frm) {
	if (frm.is_new()) return;
	frm.add_custom_button(__("Print PDF"), () => {
		const query = $.param({ doctype: frm.doctype, name: frm.docname, format: PRINT_FORMAT, no_letterhead: 1 });
		window.open(`/api/method/frappe.utils.print_format.download_pdf?${query}`);
	});
}

// Total Final Amount = Total - Total Hamali - Additional Discount Amount.
function set_total_final_amount(frm) {
	const amount = flt(flt(frm.doc.total) - flt(frm.doc.total_hamali) - flt(frm.doc.discount_amount), precision("total_final_amount", frm.doc));
	if (flt(frm.doc.total_final_amount) !== amount || frm.doc.total_final_amount == null) {
		frm.set_value("total_final_amount", amount);
	}
}

// A Trip row starts with Avg Wt 25, or 29 when its Quality is a Lot Delivery one (Lot Delivery, 25% / 10% Broken Lot Delivery).
// The user can change it: only an empty value or one of these two defaults is replaced, so a typed value stays.
function set_default_avg_wt(cdt, cdn) {
	const row = cdt && locals[cdt] && locals[cdt][cdn];
	if (!row || row.uom !== TRIP_UOM) return;
	const wanted = (row.quality || "").includes("Lot Delivery") ? LOT_DELIVERY_AVG_WT : DEFAULT_AVG_WT;
	const current = flt(row.avg_wt);
	if (current !== wanted && [0, DEFAULT_AVG_WT, LOT_DELIVERY_AVG_WT].includes(current)) {
		frappe.model.set_value(cdt, cdn, "avg_wt", wanted);
	}
}

function recalculate(frm) {
	if (frm.cscript && frm.cscript.calculate_taxes_and_totals) frm.cscript.calculate_taxes_and_totals();
}

// ERPNext works the Total out after the Items change, so the Total Final Amount follows its calculation.
function follow_erpnext_total(frm) {
	const script = frm.cscript;
	if (!script || script.__po_final_amount || !script.calculate_taxes_and_totals) return;
	const calculate = script.calculate_taxes_and_totals;
	script.calculate_taxes_and_totals = async function () {
		const result = await calculate.apply(this, arguments);
		set_total_final_amount(frm);
		return result;
	};
	// A Trip row's Amount is Quantity x Avg Wt(MT) x 10 x Rate: the Rate is per quintal and 1 MT is 10 quintal (ERPNext's own step gives Quantity x Rate).
	const calculate_item_values = script.calculate_item_values;
	if (calculate_item_values) {
		script.calculate_item_values = function () {
			const result = calculate_item_values.apply(this, arguments);
			if (!this.discount_amount_applied) {
				(frm.doc.items || []).forEach((item) => {
					if (item.uom !== TRIP_UOM) return;
					item.net_amount = item.amount = flt(flt(item.qty) * flt(item.avg_wt) * QUINTAL_PER_MT * flt(item.rate), precision("amount", item));
					item.base_amount = flt(item.amount * flt(frm.doc.conversion_rate || 1), precision("base_amount", item));
					item.base_net_amount = item.base_amount;
				});
			}
			return result;
		};
	}
	script.__po_final_amount = true;
}

function set_total_hamali(frm) {
	if (frm.doc.hamali_payer !== "Yes") {
		frm.set_value("total_hamali", 0);
		set_total_final_amount(frm);
		return;
	}
	const bags = (frm.doc.items || [])
		.filter((row) => HAMALI_UOMS.includes(row.uom))
		.reduce((sum, row) => sum + flt(row.qty), 0);
	frm.set_value("total_hamali", bags * flt(frm.doc.hamali_rate));
	set_total_final_amount(frm);
}
