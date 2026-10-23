// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Season Master", {
	crop_season(frm) {
		sync_year_name_and_code(frm);
	},
	start_date(frm) {
		sync_year_name_and_code(frm);
	},
});

// Same rules as SeasonMaster._sync_year_name_and_code on the server.
function sync_year_name_and_code(frm) {
	// A saved season keeps its name; the server checks any change on save.
	if (!frm.is_new()) return;
	const year = frm.doc.start_date ? season_year(frm) : (frm.doc.year || "").trim();
	frm.set_value("year", year);
	const season_name = frm.doc.crop_season && year ? `${frm.doc.crop_season} ${year}` : "";
	frm.set_value("season_name", season_name);
	frm.set_value("season_code", season_code(frm.doc.crop_season, year));
}

// Kharif takes the Start Date year; Rabi follows Kharif but belongs to the previous year.
function season_year(frm) {
	const start_year = parseInt(frm.doc.start_date.slice(0, 4), 10);
	return String(frm.doc.crop_season === "Rabi" ? start_year - 1 : start_year);
}

// Kharif 2025 -> K25, Rabi 2026 -> R26 (short_season_code on the server).
function season_code(crop_season, year) {
	const prefix = { Kharif: "K", Rabi: "R" }[crop_season];
	const full_year = (year.match(/\d{4}/) || [])[0];
	return prefix && full_year ? prefix + full_year.slice(-2) : "";
}
