// Copyright (c) 2026, Profezzo and contributors

// Filters, links and "Portal View" are shared: public/js/portal_detail_table.bundle.js.
// Details and AC Note Doc columns download the files saved from those buttons.
// season_filter: Mill and Season filters on top; Season keeps the DCs View DC from DCRO shows with it.
// edit_ac_note_values: rows whose AC Note gives no Date of Acceptance get their Accepted Date and Net Weight by hand.
frappe.query_reports["DC Transit Challan from DCRO"] = ivri_od.portal.section_report_settings({
	edit_ac_note_values: true,
	season_filter: true,
});
