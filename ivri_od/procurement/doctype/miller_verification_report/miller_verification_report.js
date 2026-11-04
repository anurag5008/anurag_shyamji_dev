// Copyright (c) 2026, Profezzo and contributors

// Annexure-1 with one column per District and Season (Kharif / Rabi) of the KMS Year. Only the
// Present Verification Date, V. Paddy Milled during the week and FRK are typed in: get_figures
// works out the other figures from the portal data (Transit Passes, Paddy Release, View DC,
// DC Transit Challan, Lot Search) and gives the last report's VI / X, and this script shows them with the
// calculated rows and totals. The same is done on save in
// miller_verification_report.py.
// A new report is filled from the last submitted report of the same Miller Code and KMS Year
// (get_last_report), so the same details and columns are not added every week.
// A draft also gets a column for every District and Season of the KMS Year with portal data of the
// mill (get_data_columns): only missing columns are added, none is removed.
frappe.provide("ivri_od.mvr");

const MVR_PRECISION = 3;
const MVR_METHOD = "ivri_od.procurement.doctype.miller_verification_report.miller_verification_report";
// Column figures worked out on the server (SOURCE_FIELDS in miller_verification_report.py).
const MVR_SOURCE_FIELDS = [
	"paddy_received_week",
	"prog_paddy_received",
	"paddy_released_week",
	"prog_paddy_released",
	"rice_delivered_week_fci",
	"rice_delivered_week_rrc",
	"prog_dc_fci",
	"prog_dc_rrc",
	"prog_delivered_fci",
	"prog_delivered_rrc",
];
// Typed in: no source yet.
const MVR_TYPED_FIELDS = ["paddy_milled_week", "frk_percent", "frk_qty"];

// Agency quantities with a "total_<field>" on the report (FRK % is not added up).
const MVR_TOTAL_FIELDS = [
	"paddy_received_week",
	"prog_paddy_received",
	"paddy_released_week",
	"prog_paddy_released",
	"paddy_milled_week",
	"prog_paddy_milled",
	"book_balance_paddy",
	"verified_balance_paddy",
	"paddy_difference",
	"rice_received_week",
	"prog_rice_received",
	"frk_qty",
	"prog_cmr_due",
	"rice_delivered_week_fci",
	"rice_delivered_week_rrc",
	"rice_delivered_week_total",
	"prog_dc_fci",
	"prog_dc_rrc",
	"prog_dc_total",
	"prog_delivered_fci",
	"prog_delivered_rrc",
	"prog_delivered_total",
	"undelivered_fci",
	"undelivered_rrc",
	"undelivered_total",
	"book_balance_rice",
	"verified_balance_rice",
	"rice_difference",
];

// The Annexure-1 format shown on the form (rows I-XVI down, agencies across, as the print
// format): [Sl. No., particulars, FCI / RRC / TOTAL, field, rows the Sl. No. spans (0 = spanned)].
// Group lines are [group name].
const MVR_FORMAT = [
	["PADDY"],
	["I", "Paddy Procured/Received during the week", "", "paddy_received_week", 1],
	["II", "Prog. Paddy Procured/Received till verification date", "", "prog_paddy_received", 1],
	["III", "Paddy Released for Milling during the week", "", "paddy_released_week", 1],
	["IV", "Prog. Paddy Released for Milling till verification date", "", "prog_paddy_released", 1],
	["V", "Paddy Milled during the week", "", "paddy_milled_week", 1],
	["VI", "Prog. Paddy Milled till verification date", "", "prog_paddy_milled", 1],
	["VII", "Book balance of Paddy Stock", "", "book_balance_paddy", 1],
	["VIII", "Verified balance of Paddy", "", "verified_balance_paddy", 1],
	["RICE"],
	["IX", "Rice received from milling till date", "", "rice_received_week", 1],
	["X", "Prog. Rice received from milling till date", "", "prog_rice_received", 1],
	["", "FRK %", "", "frk_percent", 1],
	["", "FRK Quantity", "", "frk_qty", 1],
	["", "Prog. CMR Due", "", "prog_cmr_due", 1],
	["XI", "Rice delivered during the week against DC", "FCI", "rice_delivered_week_fci", 3],
	["", "", "RRC", "rice_delivered_week_rrc", 0],
	["", "", "TOTAL", "rice_delivered_week_total", 0],
	["XII", "Prog. DC issued till verification", "FCI", "prog_dc_fci", 3],
	["", "", "RRC", "prog_dc_rrc", 0],
	["", "", "TOTAL", "prog_dc_total", 0],
	["XIII", "Prog. Rice delivered against total DC issued", "FCI", "prog_delivered_fci", 3],
	["", "", "RRC", "prog_delivered_rrc", 0],
	["", "", "TOTAL", "prog_delivered_total", 0],
	["XIV", "Balance Rice remain undelivered against DC", "FCI", "undelivered_fci", 3],
	["", "", "RRC", "undelivered_rrc", 0],
	["", "", "TOTAL", "undelivered_total", 0],
	["XV", "Book balance of Rice Stock", "", "book_balance_rice", 1],
	["XVI", "Verified balance of Rice", "", "verified_balance_rice", 1],
];

frappe.ui.form.on("Miller Verification Report", {
	setup: (frm) => {
		// Show the Mill No. (e.g. M051007), not the mill's name (Mill Master shows its name
		// in every other link); the name is in 1a. Miller Name.
		frm.fields_dict.miller_code.is_title_link = () => false;
	},
	onload: (frm) => {
		frappe.xcall(`${MVR_METHOD}.get_kms_years`).then((years) => {
			frm.set_df_property("kms", "options", years || []);
			if (frm.is_new() && !frm.doc.kms && years && years.length) frm.set_value("kms", years[0]);
		});
	},
	refresh: (frm) => {
		frm.mvr_format_signature = null;
		ivri_od.mvr.render_format(frm);
		if (frm.is_new()) {
			ivri_od.mvr.load_figures(frm);
		} else {
			ivri_od.mvr.add_data_columns(frm);
		}
	},
	miller_code: (frm) => {
		ivri_od.mvr.set_variety(frm);
		ivri_od.mvr.fill_from_last(frm);
	},
	kms: (frm) => ivri_od.mvr.fill_from_last(frm),
	present_verification_date: (frm) => ivri_od.mvr.load_figures(frm),
	last_verification_date: (frm) => ivri_od.mvr.load_figures(frm),
	meter_reading_last: (frm) => ivri_od.mvr.units_consumed(frm),
	meter_reading_present: (frm) => ivri_od.mvr.units_consumed(frm),
	meter_multiplier: (frm) => ivri_od.mvr.units_consumed(frm),
	agencies_remove: (frm) => ivri_od.mvr.all_rows(frm),
});

frappe.ui.form.on("Miller Verification Agency", {
	district: (frm) => ivri_od.mvr.load_figures(frm),
	season: (frm) => ivri_od.mvr.load_figures(frm),
	paddy_milled_week: (frm) => ivri_od.mvr.all_rows(frm),
	frk_percent: (frm) => ivri_od.mvr.all_rows(frm),
	frk_qty: (frm) => ivri_od.mvr.all_rows(frm),
});

ivri_od.mvr.round = (value) => flt(value, MVR_PRECISION);

// 2b. Variety from the Type of the mill (Boiled -> Par-Boiled, Raw -> Raw).
ivri_od.mvr.set_variety = function (frm) {
	if (!frm.doc.miller_code || frm.doc.docstatus !== 0) return;
	frappe.db.get_value("Mill Master", frm.doc.miller_code, "type").then((r) => {
		const type = ((r.message && r.message.type) || "").trim().toLowerCase();
		const variety = { boiled: "Par-Boiled", raw: "Raw" }[type];
		if (variety && variety !== frm.doc.variety) frm.set_value("variety", variety);
	});
};

// New report: fill the empty fields and the District / Season columns from the last submitted
// report of the same Miller Code and KMS Year; its date and present meter reading become the last ones.
ivri_od.mvr.fill_from_last = function (frm) {
	if (!frm.is_new()) {
		ivri_od.mvr.add_data_columns(frm);
		return;
	}
	if (!frm.doc.miller_code || !frm.doc.kms) {
		ivri_od.mvr.load_figures(frm);
		return;
	}
	frappe
		.xcall(`${MVR_METHOD}.get_last_report`, {
			miller_code: frm.doc.miller_code,
			kms: frm.doc.kms,
			name: frm.doc.name,
		})
		.then((last) => {
			const { agencies, last_report, ...values } = last || {};
			const empty = {};
			Object.entries(values).forEach(([field, value]) => {
				if (value !== null && value !== undefined && value !== "" && !frm.doc[field]) empty[field] = value;
			});
			if (agencies && agencies.length && !(frm.doc.agencies || []).length) {
				agencies.forEach((row) =>
					frm.add_child("agencies", { district: row.district, season: row.season, agency: row.district })
				);
				frm.refresh_field("agencies");
			}
			return frm.set_value(empty).then(() => {
				if (last_report) {
					frappe.show_alert({ message: __("Filled from {0}.", [last_report]), indicator: "green" });
				}
				ivri_od.mvr.add_data_columns(frm);
			});
		});
};

// Draft: add a column for each District and Season of the KMS Year that has portal data of the
// mill and is not in Annexure-1 yet, then load the figures.
ivri_od.mvr.add_data_columns = function (frm) {
	if (frm.doc.docstatus !== 0 || !frm.doc.miller_code || !frm.doc.kms) {
		ivri_od.mvr.load_figures(frm);
		return;
	}
	const call = (frm.mvr_columns_call = frappe.xcall(`${MVR_METHOD}.get_data_columns`, {
		miller_code: frm.doc.miller_code,
		kms: frm.doc.kms,
	}));
	call.then((columns) => {
		if (call !== frm.mvr_columns_call) return; // an older call answered after a newer one
		const key = (district, season) => `${(district || "").replace(/\s/g, "").toLowerCase()}|${season || ""}`;
		const have = new Set((frm.doc.agencies || []).map((row) => key(row.district, row.season)));
		const added = (columns || []).filter((c) => !have.has(key(c.district, c.season)));
		added.forEach((c) => frm.add_child("agencies", { district: c.district, season: c.season, agency: c.district }));
		if (added.length) {
			frm.refresh_field("agencies");
			frm.dirty();
			frappe.show_alert({
				message: __("Added from the portal data: {0}.", [added.map((c) => `${c.district} ${c.season}`).join(", ")]),
				indicator: "blue",
			});
		}
		ivri_od.mvr.load_figures(frm);
	});
};

// The figures of every column, worked out on the server from the portal data.
ivri_od.mvr.load_figures = function (frm) {
	const rows = frm.doc.agencies || [];
	if (frm.doc.docstatus !== 0 || !frm.doc.miller_code || !frm.doc.kms || !frm.doc.present_verification_date || !rows.length) {
		ivri_od.mvr.all_rows(frm);
		return;
	}
	const call = (frm.mvr_call = frappe.xcall(`${MVR_METHOD}.get_figures`, {
		miller_code: frm.doc.miller_code,
		kms: frm.doc.kms,
		present_verification_date: frm.doc.present_verification_date,
		last_verification_date: frm.doc.last_verification_date || "",
		columns: rows.map((row) => ({ district: row.district, season: row.season })),
		name: frm.doc.name,
	}));
	call.then((r) => {
		if (call !== frm.mvr_call) return; // an older call answered after a newer one
		// The last report's VI / X of each column and the Rice Percentage, used by ivri_od.mvr.agency.
		frm.mvr_last = {};
		(frm.doc.agencies || []).forEach((row, i) => {
			Object.assign(row, (r.rows || [])[i] || {});
			frm.mvr_last[row.name] = (r.last || [])[i] || {};
		});
		frm.mvr_rice_percentage = flt(r.rice_percentage);
		// Data up to the day before the Present Verification Date; from the Last Verification Date's own day.
		const week = r.last_verification_date
			? __("Period: from {0} up to {1} (the day before the Present Verification Date).", [frappe.datetime.str_to_user(r.last_verification_date), frappe.datetime.str_to_user(r.data_up_to)])
			: __("Period: everything up to {0} (the day before the Present Verification Date; no earlier report).", [frappe.datetime.str_to_user(r.data_up_to)]);
		frm.set_intro(); // each call adds a note: clear the one from the last load first
		frm.set_intro(week, "blue");
		(r.notes || []).forEach((note) => frm.set_intro(frappe.utils.escape_html(note), "orange"));
		ivri_od.mvr.all_rows(frm);
	});
};

ivri_od.mvr.units_consumed = function (frm) {
	const multiplier = frm.doc.meter_multiplier === null || frm.doc.meter_multiplier === undefined ? 1 : flt(frm.doc.meter_multiplier);
	// 0 until the present reading is typed in (not a minus figure).
	const units = frm.doc.meter_reading_present
		? (flt(frm.doc.meter_reading_present) - flt(frm.doc.meter_reading_last)) * multiplier
		: 0;
	frm.set_value("total_units_consumed", ivri_od.mvr.round(units));
};

// The calculated rows of every column, then the totals.
ivri_od.mvr.all_rows = function (frm) {
	if (frm.doc.docstatus !== 0) return ivri_od.mvr.render_format(frm);
	(frm.doc.agencies || []).forEach((row) =>
		ivri_od.mvr.agency(row, (frm.mvr_last || {})[row.name] || {}, frm.mvr_rice_percentage)
	);
	frm.refresh_field("agencies");
	ivri_od.mvr.totals(frm);
	ivri_od.mvr.render_format(frm);
};

// The format with a box to type in for FRK; every other figure is filled by the system.
// Built again only when the columns change, else the figures are updated in place (so the
// cursor stays where it is while typing).
ivri_od.mvr.render_format = function (frm) {
	const wrapper = frm.fields_dict.annexure_entry && frm.fields_dict.annexure_entry.$wrapper;
	if (!wrapper) return;
	const rows = frm.doc.agencies || [];
	const editable = frm.doc.docstatus === 0;
	const signature = JSON.stringify([rows.map((row) => [row.name, row.district, row.season]), editable]);
	if (signature !== frm.mvr_format_signature) {
		frm.mvr_format_signature = signature;
		ivri_od.mvr.build_format(frm, wrapper, rows, editable);
	}
	wrapper.find("[data-field]").each(function () {
		const row = rows.find((r) => r.name === this.dataset.row);
		const value = row ? row[this.dataset.field] : null;
		if (this.tagName === "INPUT") {
			if (this !== document.activeElement) this.value = value === null || value === undefined ? "" : value;
		} else {
			this.textContent = ivri_od.mvr.show(value);
		}
	});
	// Added up from the rows here: the report's total_ fields are set a moment later.
	wrapper.find("[data-total]").each(function () {
		const field = this.dataset.total;
		this.textContent = ivri_od.mvr.show(ivri_od.mvr.round(rows.reduce((sum, row) => sum + flt(row[field]), 0)));
	});
};

ivri_od.mvr.show = (value) => (value === null || value === undefined || value === "" ? "" : format_number(value, null, 3));

ivri_od.mvr.build_format = function (frm, wrapper, rows, editable) {
	const esc = frappe.utils.escape_html;
	const add = editable
		? `<div class="text-right mb-2"><button class="btn btn-xs btn-default mvr-add">+ ${__("District and Season")}</button></div>`
		: "";
	ivri_od.mvr.bind_format(frm, wrapper);
	if (!rows.length) {
		wrapper.html(`${add}<p class="text-muted small">${__("Add a District and Season to fill the Annexure-1 figures.")}</p>`);
		return;
	}
	const body = MVR_FORMAT.map((line) => {
		if (line.length === 1) {
			return `<tr class="mvr-group"><td colspan="${rows.length + 4}">${esc(__(line[0]))}</td></tr>`;
		}
		const [sl, particulars, part, field, span] = line;
		const head = span
			? `<td rowspan="${span}" class="text-center">${sl}</td><td rowspan="${span}"${part ? "" : ' colspan="2"'}>${esc(__(particulars))}</td>`
			: "";
		const cells = rows
			.map((row) =>
				editable && MVR_TYPED_FIELDS.includes(field)
					? `<td><input type="number" step="any" class="form-control input-xs text-right" data-row="${esc(row.name)}" data-field="${field}"></td>`
					: `<td class="mvr-auto text-right" data-row="${esc(row.name)}" data-field="${field}"></td>`
			)
			.join("");
		const total = field === "frk_percent" ? "<td></td>" : `<td class="mvr-auto text-right" data-total="${field}"></td>`;
		return `<tr>${head}${part ? `<td class="text-center">${part}</td>` : ""}${cells}${total}</tr>`;
	}).join("");
	const columns = rows
		.map((row) => {
			const name = esc(row.district || "");
			const season = `<br><small class="text-muted">${esc(row.season || "")}</small>`;
			if (!editable) return `<th class="text-center">${name}${season}</th>`;
			return `<th class="text-center text-nowrap">
				<a class="mvr-rename" data-row="${esc(row.name)}" title="${__("Change District or Season")}">${name}</a>
				<a class="mvr-remove text-muted ml-2" data-row="${esc(row.name)}" title="${__("Remove")}">&times;</a>${season}</th>`;
		})
		.join("");
	wrapper.html(`${add}
		<style>
			.mvr-format td, .mvr-format th { vertical-align: middle; padding: 4px 6px; }
			.mvr-format .mvr-group td { font-weight: 600; background: var(--subtle-fg); }
			.mvr-format .mvr-auto { background: var(--subtle-accent); color: var(--text-muted); }
			.mvr-format input { min-width: 110px; background: var(--fg-color); border: 1px solid var(--primary); }
		</style>
		<div class="table-responsive"><table class="table table-bordered mvr-format">
			<thead><tr><th style="width:60px">${__("Sl. No.")}</th><th colspan="2">${__("PARTICULARS")}</th>${columns}<th class="text-center">${__("TOTAL")}</th></tr></thead>
			<tbody>${body}</tbody>
		</table></div>
		${editable ? `<p class="text-muted small">${__("Grey figures are worked out from the portal data up to the Present Verification Date; type V. Paddy Milled during the week and FRK in the white boxes.")}</p>` : ""}`);
};

// District (District Master; the mill's District to start with) and Season (Kharif / Rabi).
ivri_od.mvr.column_fields = (district, season) => [
	{
		fieldname: "district",
		fieldtype: "Link",
		options: "District Master",
		label: __("District"),
		reqd: 1,
		default: district,
		get_query: () => ({ filters: { is_active: 1 } }),
	},
	{ fieldname: "season", fieldtype: "Select", options: "Kharif\nRabi", label: __("Season"), reqd: 1, default: season || "Kharif" },
];

// Typing FRK, and the add / change / remove District and Season buttons of the format.
ivri_od.mvr.bind_format = function (frm, wrapper) {
	const taken = (district, season, except) =>
		(frm.doc.agencies || []).some((r) => r.name !== except && r.district === district && r.season === season);
	wrapper
		.off(".mvr")
		.on("change.mvr", "input[data-field]", function () {
			frappe.model.set_value("Miller Verification Agency", this.dataset.row, this.dataset.field, flt(this.value));
		})
		.on("click.mvr", ".mvr-add", async () => {
			const mill_district = frm.doc.miller_code
				? (await frappe.db.get_value("Mill Master", frm.doc.miller_code, "district")).message?.district
				: "";
			frappe.prompt(
				ivri_od.mvr.column_fields(mill_district || "", "Kharif"),
				(v) => {
					if (taken(v.district, v.season)) {
						frappe.msgprint(__("{0} {1} is already in Annexure-1.", [v.district, v.season]));
						return;
					}
					frm.add_child("agencies", { district: v.district, season: v.season, agency: v.district });
					frm.dirty();
					ivri_od.mvr.load_figures(frm);
				},
				__("Add District and Season"),
				__("Add")
			);
		})
		.on("click.mvr", ".mvr-rename", function () {
			const row = locals["Miller Verification Agency"][this.dataset.row];
			frappe.prompt(
				ivri_od.mvr.column_fields(row.district, row.season),
				(v) => {
					if (taken(v.district, v.season, row.name)) {
						frappe.msgprint(__("{0} {1} is already in Annexure-1.", [v.district, v.season]));
						return;
					}
					Object.assign(row, { district: v.district, season: v.season, agency: v.district });
					frm.dirty();
					ivri_od.mvr.load_figures(frm);
				},
				__("Change District or Season"),
				__("Save")
			);
		})
		.on("click.mvr", ".mvr-remove", function () {
			const row = locals["Miller Verification Agency"][this.dataset.row];
			frappe.confirm(
				__("Remove {0} {1} and its figures?", [frappe.utils.escape_html(row.district || ""), row.season || ""]),
				() => {
					frappe.model.clear_doc(row.doctype, row.name); // also takes it out of the report's agencies
					frm.dirty();
					ivri_od.mvr.all_rows(frm);
				}
			);
		});
};

// Same sums as calculate_agency in miller_verification_report.py: VI / X are the last
// report's figures (last) + this week's; IX is V x the Rice Percentage (CMR %).
ivri_od.mvr.agency = function (row, last, percentage) {
	const r = ivri_od.mvr.round;
	const v = (field) => flt(row[field]);
	row.prog_paddy_milled = r(flt(last.prog_paddy_milled) + v("paddy_milled_week"));
	row.rice_received_week = r((v("paddy_milled_week") * flt(percentage)) / 100);
	row.prog_rice_received = r(flt(last.prog_rice_received) + row.rice_received_week);
	row.book_balance_paddy = r(v("prog_paddy_received") - v("prog_paddy_milled"));
	row.verified_balance_paddy = row.book_balance_paddy;
	row.paddy_difference = 0;
	row.prog_cmr_due = r(v("prog_rice_received"));
	row.rice_delivered_week_total = r(v("rice_delivered_week_fci") + v("rice_delivered_week_rrc"));
	row.prog_dc_total = r(v("prog_dc_fci") + v("prog_dc_rrc"));
	row.prog_delivered_total = r(v("prog_delivered_fci") + v("prog_delivered_rrc"));
	row.undelivered_fci = r(v("prog_dc_fci") - v("prog_delivered_fci"));
	row.undelivered_rrc = r(v("prog_dc_rrc") - v("prog_delivered_rrc"));
	row.undelivered_total = r(row.undelivered_fci + row.undelivered_rrc);
	row.book_balance_rice = r(v("prog_rice_received") - row.prog_delivered_total);
	row.verified_balance_rice = row.book_balance_rice;
	row.rice_difference = 0;
};

ivri_od.mvr.totals = function (frm) {
	const values = {};
	MVR_TOTAL_FIELDS.forEach((field) => {
		values[`total_${field}`] = ivri_od.mvr.round(
			(frm.doc.agencies || []).reduce((sum, row) => sum + flt(row[field]), 0)
		);
	});
	frm.set_value(values);
};
