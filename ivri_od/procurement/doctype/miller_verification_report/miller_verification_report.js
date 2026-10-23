// Copyright (c) 2026, Profezzo and contributors

// Shows the calculated rows (IV, V, VI, VII, VIII, CMR Due, X-XIV), the totals and 4d Units
// consumed while typing. The same sums are made on save in miller_verification_report.py.
// Progressive rows carry on from the previous submitted report of the same Miller Code and
// KMS: get_progressive_basis gives it, with the FCI rice %, the paddy of Target Allocation
// (II) and the DC quantities (X) of the rows' seasons.
// A new report is filled from the last submitted report of the same Miller Code and Season
// (get_last_report), so the same details are not typed in every week.
frappe.provide("ivri_od.mvr");

const MVR_PRECISION = 3;
// Agency fields that change a calculated field.
const MVR_AGENCY_INPUTS = [
	"agency",
	"paddy_received_week",
	"prog_paddy_received",
	"prog_paddy_milled",
	"rice_received_week",
	"prog_rice_received",
	"frk_qty",
	"rice_delivered_week_fci",
	"rice_delivered_week_rrc",
	"prog_dc_fci",
	"prog_dc_rrc",
	"prog_delivered_fci",
	"prog_delivered_rrc",
];
// Progressive field: this week's field added to the previous report's value.
const MVR_PROGRESSIVE = {
	prog_paddy_milled: "paddy_milled_week",
	prog_rice_received: "rice_received_week",
	prog_delivered_fci: "rice_delivered_week_fci",
	prog_delivered_rrc: "rice_delivered_week_rrc",
};
// Agency quantities with a "total_<field>" on the report (FRK % is not added up).
const MVR_TOTAL_FIELDS = [
	"paddy_received_week",
	"prog_paddy_received",
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

// The Annexure-1 format shown on the form (rows I-XIV down, agencies across, as the print
// format): [Sl. No., particulars, FCI / RRC / TOTAL, field, rows the Sl. No. spans (0 = spanned)].
// Group lines are [group name].
const MVR_FORMAT = [
	["PADDY"],
	["I", "Paddy Procured/Received during the week", "", "paddy_received_week", 1],
	["II", "Prog. Paddy Procured/Received till verification date", "", "prog_paddy_received", 1],
	["III", "Paddy Milled during the week", "", "paddy_milled_week", 1],
	["IV", "Prog. Paddy Milled till verification date", "", "prog_paddy_milled", 1],
	["V", "Book balance of Paddy Stock", "", "book_balance_paddy", 1],
	["VI", "Verified balance of Paddy", "", "verified_balance_paddy", 1],
	["RICE"],
	["VII", "Rice received from milling till date", "", "rice_received_week", 1],
	["VIII", "Prog. Rice received from milling till date", "", "prog_rice_received", 1],
	["", "FRK %", "", "frk_percent", 1],
	["", "FRK Quantity", "", "frk_qty", 1],
	["", "Prog. CMR Due", "", "prog_cmr_due", 1],
	["IX", "Rice delivered during the week against DC", "FCI", "rice_delivered_week_fci", 2],
	["", "", "RRC", "rice_delivered_week_rrc", 0],
	["X", "Prog. DC issued till verification", "FCI", "prog_dc_fci", 3],
	["", "", "RRC", "prog_dc_rrc", 0],
	["", "", "TOTAL", "prog_dc_total", 0],
	["XI", "Prog. Rice delivered against total DC issued", "FCI", "prog_delivered_fci", 3],
	["", "", "RRC", "prog_delivered_rrc", 0],
	["", "", "TOTAL", "prog_delivered_total", 0],
	["XII", "Balance Rice remain undelivered against DC", "FCI", "undelivered_fci", 3],
	["", "", "RRC", "undelivered_rrc", 0],
	["", "", "TOTAL", "undelivered_total", 0],
	["XIII", "Book balance of Rice Stock", "", "book_balance_rice", 1],
	["XIV", "Verified balance of Rice", "", "verified_balance_rice", 1],
];

frappe.ui.form.on("Miller Verification Report", {
	setup: (frm) => {
		// Show the Mill No. (e.g. M051007), not the mill's name (Mill Master shows its name
		// in every other link); the name is in 1a. Miller Name.
		frm.fields_dict.miller_code.is_title_link = () => false;
	},
	refresh: (frm) => {
		frm.mvr_format_signature = null;
		frm.mvr_season = frm.doc.season;
		ivri_od.mvr.load_basis(frm);
		ivri_od.mvr.render_format(frm);
	},
	miller_code: (frm) => ivri_od.mvr.fill_from_last(frm),
	season: (frm) => {
		// Agencies of the report's old season (or none) move to the new one; an agency given
		// its own season keeps it.
		(frm.doc.agencies || []).forEach((row) => {
			if (!row.season || row.season === frm.mvr_season) row.season = frm.doc.season;
		});
		frm.mvr_season = frm.doc.season;
		ivri_od.mvr.fill_from_last(frm);
	},
	kms: (frm) => ivri_od.mvr.load_basis(frm),
	variety: (frm) => ivri_od.mvr.load_basis(frm),
	present_verification_date: (frm) => ivri_od.mvr.load_basis(frm),
	meter_reading_last: (frm) => ivri_od.mvr.units_consumed(frm),
	meter_reading_present: (frm) => ivri_od.mvr.units_consumed(frm),
	meter_multiplier: (frm) => ivri_od.mvr.units_consumed(frm),
	agencies_remove: (frm) => ivri_od.mvr.all_rows(frm),
});

const mvr_agency_events = {
	agencies_add: (frm, cdt, cdn) => {
		const row = locals[cdt][cdn];
		if (!row.season && frm.doc.season) row.season = frm.doc.season;
		ivri_od.mvr.all_rows(frm);
	},
	// A new season needs its Target Allocation paddy (II) and DC quantities (X).
	season: (frm) => ivri_od.mvr.load_basis(frm),
	// III changed: VII is worked out again from the FCI rice % (Par-Boiled), then the rest.
	paddy_milled_week: (frm, cdt, cdn) => {
		const row = locals[cdt][cdn];
		const pct = frm.mvr_basis && frm.mvr_basis.rice_percentage;
		if (pct !== null && pct !== undefined) {
			row.rice_received_week = ivri_od.mvr.round((flt(row.paddy_milled_week) * flt(pct)) / 100);
		}
		ivri_od.mvr.all_rows(frm);
	},
};
MVR_AGENCY_INPUTS.forEach((field) => {
	mvr_agency_events[field] = (frm) => ivri_od.mvr.all_rows(frm);
});
frappe.ui.form.on("Miller Verification Agency", mvr_agency_events);

ivri_od.mvr.round = (value) => flt(value, MVR_PRECISION);
ivri_od.mvr.row_key = (row) => `${(row.agency || "").trim().toLowerCase()}|${row.season || ""}`;

// New report: fill the empty fields and the agencies from the last submitted report of the
// same Miller Code and Season; its date and present meter reading become the last ones here.
ivri_od.mvr.fill_from_last = function (frm) {
	if (!frm.is_new() || !frm.doc.miller_code || !frm.doc.season) {
		ivri_od.mvr.load_basis(frm);
		return;
	}
	frappe
		.xcall("ivri_od.procurement.doctype.miller_verification_report.miller_verification_report.get_last_report", {
			miller_code: frm.doc.miller_code,
			season: frm.doc.season,
			name: frm.doc.name,
		})
		.then((last) => {
			const { agencies, last_report, ...values } = last || {};
			const empty = {};
			Object.entries(values).forEach(([field, value]) => {
				if (value !== null && value !== undefined && value !== "" && !frm.doc[field]) empty[field] = value;
			});
			const no_rows = !(frm.doc.agencies || []).some((row) => row.agency);
			if (agencies && agencies.length && no_rows) {
				frm.clear_table("agencies");
				agencies.forEach((row) => frm.add_child("agencies", { agency: row.agency, season: row.season }));
			}
			(frm.doc.agencies || []).forEach((row) => {
				if (!row.season) row.season = frm.doc.season;
			});
			frm.refresh_field("agencies");
			return frm.set_value(empty).then(() => {
				if (last_report) {
					frappe.show_alert({ message: __("Filled from {0}.", [last_report]), indicator: "green" });
				}
				ivri_od.mvr.load_basis(frm);
			});
		});
};

// The previous report, FCI rice % and DC quantities; only while the report can be changed.
ivri_od.mvr.load_basis = function (frm) {
	frm.mvr_basis = null;
	if (frm.doc.docstatus !== 0 || !frm.doc.miller_code || !frm.doc.kms) {
		ivri_od.mvr.set_progressive_read_only(frm, false);
		ivri_od.mvr.render_format(frm);
		return;
	}
	frappe
		.xcall("ivri_od.procurement.doctype.miller_verification_report.miller_verification_report.get_progressive_basis", {
			miller_code: frm.doc.miller_code,
			kms: frm.doc.kms,
			variety: frm.doc.variety || "",
			present_verification_date: frm.doc.present_verification_date || "",
			name: frm.doc.name,
			seasons: [...new Set((frm.doc.agencies || []).map((row) => row.season).filter(Boolean))],
		})
		.then((basis) => {
			frm.mvr_basis = basis;
			// With a previous report IV, VIII and XI are carried on, not typed in.
			ivri_od.mvr.set_progressive_read_only(frm, !!basis.previous);
			frm.set_intro(); // each call adds a note: clear the one from the last load first
			frm.set_intro(
				basis.previous
					? __("Progressive figures carry on from {0}.", [`<b>${frappe.utils.escape_html(basis.previous)}</b>`])
					: __("First report of this miller and KMS."),
				"blue"
			);
			ivri_od.mvr.all_rows(frm);
		});
};

ivri_od.mvr.set_progressive_read_only = function (frm, read_only) {
	const grid = frm.fields_dict.agencies.grid;
	Object.keys(MVR_PROGRESSIVE).forEach((field) => grid.update_docfield_property(field, "read_only", read_only ? 1 : 0));
	frm.refresh_field("agencies");
};

ivri_od.mvr.units_consumed = function (frm) {
	const multiplier = frm.doc.meter_multiplier === null || frm.doc.meter_multiplier === undefined ? 1 : flt(frm.doc.meter_multiplier);
	// 0 until the present reading is typed in (not a minus figure).
	const units = frm.doc.meter_reading_present
		? (flt(frm.doc.meter_reading_present) - flt(frm.doc.meter_reading_last)) * multiplier
		: 0;
	frm.set_value("total_units_consumed", ivri_od.mvr.round(units));
};

// Every row (II and X go to the first row of each season), then the totals.
ivri_od.mvr.all_rows = function (frm) {
	if (frm.doc.docstatus !== 0) return ivri_od.mvr.render_format(frm);
	const seasons = new Set();
	(frm.doc.agencies || []).forEach((row) => {
		ivri_od.mvr.progressive(frm, row, !seasons.has(row.season));
		seasons.add(row.season);
		ivri_od.mvr.agency(row);
	});
	frm.refresh_field("agencies");
	ivri_od.mvr.totals(frm);
	ivri_od.mvr.render_format(frm);
};

// A figure the officer does not type: worked out (V, VI, CMR Due, X / XI / XII Total, XIII,
// XIV), carried on from the previous report (IV, VIII, XI), or read from Target Allocation
// (II) and the DCs (X) on the first row of the season.
ivri_od.mvr.is_auto = function (frm, row, field, first_of_season) {
	if (frappe.meta.get_docfield("Miller Verification Agency", field).read_only) return true;
	const basis = frm.mvr_basis;
	if (!basis) return false;
	// Carried on from the previous report (0 for an agency it did not have).
	if (basis.previous && MVR_PROGRESSIVE[field]) return true;
	if (!first_of_season) return false;
	if (field === "prog_paddy_received") return (basis.paddy_received || {})[row.season] !== undefined;
	if (field === "prog_dc_fci" || field === "prog_dc_rrc") return !!(basis.dc_quantity || {})[row.season];
	return false;
};

// The format with a box to type in for each figure the officer enters; the rest is shown.
// Built again only when the agencies or the open boxes change, else the figures are
// updated in place (so the cursor stays where it is while typing).
ivri_od.mvr.render_format = function (frm) {
	const wrapper = frm.fields_dict.annexure_entry && frm.fields_dict.annexure_entry.$wrapper;
	if (!wrapper) return;
	const rows = frm.doc.agencies || [];
	const editable = frm.doc.docstatus === 0;
	const seen = new Set();
	const first = rows.map((row) => {
		const is_first = !seen.has(row.season);
		seen.add(row.season);
		return is_first;
	});
	const lines = MVR_FORMAT.filter((line) => line.length > 1);
	const open = rows.map((row, i) =>
		lines.map((line) => (editable && !ivri_od.mvr.is_auto(frm, row, line[3], first[i]) ? 1 : 0)).join("")
	);
	const signature = JSON.stringify([rows.map((row) => [row.name, row.agency, row.season]), open, editable]);
	if (signature !== frm.mvr_format_signature) {
		frm.mvr_format_signature = signature;
		ivri_od.mvr.build_format(frm, wrapper, rows, open, editable);
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

ivri_od.mvr.build_format = function (frm, wrapper, rows, open, editable) {
	const esc = frappe.utils.escape_html;
	const add = editable
		? `<div class="text-right mb-2"><button class="btn btn-xs btn-default mvr-add">+ ${__("Add Agency")}</button></div>`
		: "";
	ivri_od.mvr.bind_format(frm, wrapper);
	if (!rows.length) {
		wrapper.html(`${add}<p class="text-muted small">${__("Add an agency to fill the Annexure-1 figures.")}</p>`);
		return;
	}
	let n = -1;
	const body = MVR_FORMAT.map((line) => {
		if (line.length === 1) {
			return `<tr class="mvr-group"><td colspan="${rows.length + 4}">${esc(__(line[0]))}</td></tr>`;
		}
		n += 1;
		const [sl, particulars, part, field, span] = line;
		const head = span
			? `<td rowspan="${span}" class="text-center">${sl}</td><td rowspan="${span}"${part ? "" : ' colspan="2"'}>${esc(__(particulars))}</td>`
			: "";
		const cells = rows
			.map((row, i) =>
				open[i][n] === "1"
					? `<td><input type="number" step="any" class="form-control input-xs text-right" data-row="${esc(row.name)}" data-field="${field}"></td>`
					: `<td class="mvr-auto text-right" data-row="${esc(row.name)}" data-field="${field}"></td>`
			)
			.join("");
		const total = field === "frk_percent" ? "<td></td>" : `<td class="mvr-auto text-right" data-total="${field}"></td>`;
		return `<tr>${head}${part ? `<td class="text-center">${part}</td>` : ""}${cells}${total}</tr>`;
	}).join("");
	const agencies = rows
		.map((row) => {
			const name = esc(row.agency || "");
			const season = `<br><small class="text-muted">${esc(row.season || "")}</small>`;
			if (!editable) return `<th class="text-center">${name}${season}</th>`;
			return `<th class="text-center text-nowrap">
				<a class="mvr-rename" data-row="${esc(row.name)}" title="${__("Change name or season")}">${name}</a>
				<a class="mvr-remove text-muted ml-2" data-row="${esc(row.name)}" title="${__("Remove agency")}">&times;</a>${season}</th>`;
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
			<thead><tr><th style="width:60px">${__("Sl. No.")}</th><th colspan="2">${__("PARTICULARS")}</th>${agencies}<th class="text-center">${__("TOTAL")}</th></tr></thead>
			<tbody>${body}</tbody>
		</table></div>
		${editable ? `<p class="text-muted small">${__("Type in the white boxes; grey figures are filled by the system.")}</p>` : ""}`);
};

// Agency name and season (from Season Master; the report's season to start with).
ivri_od.mvr.agency_fields = (agency, season) => [
	{ fieldname: "agency", fieldtype: "Data", label: __("Agency Name"), reqd: 1, default: agency },
	{ fieldname: "season", fieldtype: "Link", options: "Season Master", label: __("Season"), reqd: 1, default: season },
];

// Typing in a box, and the Add / rename / remove agency buttons of the format.
ivri_od.mvr.bind_format = function (frm, wrapper) {
	wrapper
		.off(".mvr")
		.on("change.mvr", "input[data-field]", function () {
			frappe.model.set_value("Miller Verification Agency", this.dataset.row, this.dataset.field, flt(this.value));
		})
		.on("click.mvr", ".mvr-add", () => {
			if (!frm.doc.season) {
				frappe.msgprint(__("Select the Season first."));
				return;
			}
			frappe.prompt(ivri_od.mvr.agency_fields("", frm.doc.season), (v) => {
				frm.add_child("agencies", { agency: v.agency.trim(), season: v.season });
				frm.dirty();
				ivri_od.mvr.load_basis(frm);
			}, __("Add Agency"), __("Add"));
		})
		.on("click.mvr", ".mvr-rename", function () {
			const row = locals["Miller Verification Agency"][this.dataset.row];
			frappe.prompt(
				ivri_od.mvr.agency_fields(row.agency, row.season),
				(v) => {
					row.agency = v.agency.trim();
					row.season = v.season;
					frm.dirty();
					// A new season needs its Target Allocation paddy (II) and DC quantities (X).
					ivri_od.mvr.load_basis(frm);
				},
				__("Change Agency"),
				__("Save")
			);
		})
		.on("click.mvr", ".mvr-remove", function () {
			const row = locals["Miller Verification Agency"][this.dataset.row];
			frappe.confirm(__("Remove agency {0} and its figures?", [frappe.utils.escape_html(row.agency || "")]), () => {
				frappe.model.clear_doc(row.doctype, row.name); // also takes it out of the report's agencies
				frm.dirty();
				ivri_od.mvr.all_rows(frm);
			});
		});
};

// Same as apply_progressive in miller_verification_report.py.
ivri_od.mvr.progressive = function (frm, row, first_of_season) {
	const basis = frm.mvr_basis;
	if (!basis) return;
	const r = ivri_od.mvr.round;
	if (basis.rice_percentage !== null && basis.rice_percentage !== undefined && !flt(row.rice_received_week)) {
		row.rice_received_week = r((flt(row.paddy_milled_week) * flt(basis.rice_percentage)) / 100);
	}
	if (basis.previous) {
		const previous = basis.rows[ivri_od.mvr.row_key(row)] || {};
		Object.entries(MVR_PROGRESSIVE).forEach(([prog, week]) => {
			row[prog] = r(flt(previous[prog]) + flt(row[week]));
		});
	} else {
		// First report: starts from 0 unless an opening figure is typed in.
		Object.entries(MVR_PROGRESSIVE).forEach(([prog, week]) => {
			if (!flt(row[prog])) row[prog] = r(flt(row[week]));
		});
	}
	const paddy = (basis.paddy_received || {})[row.season];
	if (paddy !== undefined && first_of_season) {
		row.prog_paddy_received = paddy;
	}
	const dc = (basis.dc_quantity || {})[row.season];
	if (dc && first_of_season) {
		row.prog_dc_fci = dc.fci;
		row.prog_dc_rrc = dc.rrc;
	}
};

// Same sums as calculate_agency in miller_verification_report.py.
ivri_od.mvr.agency = function (row) {
	const r = ivri_od.mvr.round;
	const v = (field) => flt(row[field]);
	row.book_balance_paddy = r(v("prog_paddy_received") - v("prog_paddy_milled"));
	row.verified_balance_paddy = row.book_balance_paddy;
	row.paddy_difference = 0;
	row.prog_cmr_due = r(v("prog_rice_received"));
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
