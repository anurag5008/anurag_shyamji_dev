// Open Procurement script/query reports on the data table, not the Report setup form.

const PROCUREMENT_REPORT_TYPES = ["Script Report", "Query Report", "Custom Report"];

function should_open_procurement_report_table(doc) {
	if (!doc || doc.__islocal) {
		return false;
	}
	if (doc.module !== "Procurement") {
		return false;
	}
	if (!PROCUREMENT_REPORT_TYPES.includes(doc.report_type)) {
		return false;
	}
	if (frappe.route_options && frappe.route_options.edit_report_config) {
		return false;
	}
	return true;
}

frappe.ui.form.on("Report", {
	refresh(frm) {
		if (!should_open_procurement_report_table(frm.doc)) {
			return;
		}
		frappe.set_route("query-report", frm.doc.name);
	},
});
