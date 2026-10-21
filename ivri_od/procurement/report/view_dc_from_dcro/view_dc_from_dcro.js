// Copyright (c) 2026, Profezzo and contributors

// Filters, links and "Portal View" are shared: public/js/portal_detail_table.bundle.js.
// The saved DC document is linked as "Download_DC" on its RRC or FCI cell (in place of View_RRC / View_FCI).
// details: "Show Detail Rows (Lots)" lists the number of lots read from the DC page (grdDepotFCIbody / grdDepotRRCbody, td[4]).
frappe.query_reports["View DC from DCRO"] = ivri_od.portal.section_report_settings({
	file_link_text: "Download_DC",
	details: true,
});
