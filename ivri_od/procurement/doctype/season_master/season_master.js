// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

frappe.ui.form.on("Season Master", {
	crop_season(frm) {
		set_season_name(frm);
	},
	year(frm) {
		set_season_name(frm);
	},
});

function set_season_name(frm) {
	const season_name = frm.doc.crop_season && frm.doc.year ? `${frm.doc.crop_season} ${frm.doc.year}` : "";
	frm.set_value("season_name", season_name);
}
