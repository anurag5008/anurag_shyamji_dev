// Reports of this app (Procurement): every column is as wide as its header text or its widest
// value (first SAMPLE_ROWS rows), whichever is wider, between MIN_WIDTH and MAX_WIDTH.
// The width set in a report's Python or JS is replaced. Reports of other apps are not changed.
// Done before each draw of the table, so a new filter (new data) resizes the columns again.
(function () {
	const APP = "ivri_od";
	const MIN_WIDTH = 70;
	const MAX_WIDTH = 400;
	const SAMPLE_ROWS = 200;
	// Room around the text: cell padding, and in the header the sort / dropdown button.
	const HEADER_PADDING = 44;
	const CELL_PADDING = 24;

	let canvas;
	function text_width(text, bold) {
		canvas = canvas || document.createElement("canvas");
		const ctx = canvas.getContext("2d");
		const style = getComputedStyle(document.body);
		ctx.font = `${bold ? "600 " : ""}${style.fontSize} ${style.fontFamily}`;
		return ctx.measureText(text || "").width;
	}

	function plain_text(html) {
		return $("<div>")
			.html(html == null ? "" : String(html))
			.text()
			.trim();
	}

	function is_app_report(report) {
		const module = report.report_doc && report.report_doc.module;
		return !!module && (frappe.boot.module_app || {})[frappe.scrub(module)] === APP;
	}

	function fit_columns(report) {
		const rows = (report.data || []).slice(0, SAMPLE_ROWS);
		for (const column of report.columns || []) {
			if (column.hidden) continue;
			let width = text_width(column.name || column.label, true) + HEADER_PADDING;
			for (const row of rows) {
				const value = row[column.fieldname];
				if (value == null || value === "") continue;
				const shown = plain_text(frappe.format(value, column, { always_show_decimals: true }, row));
				width = Math.max(width, text_width(shown, false) + CELL_PADDING);
			}
			column.width = Math.round(Math.min(Math.max(width, MIN_WIDTH), MAX_WIDTH));
		}
	}

	function patch_query_report() {
		const QueryReport = frappe.views && frappe.views.QueryReport;
		if (!QueryReport) return false;
		if (QueryReport.prototype.__ivri_od_column_width) return true;

		const render_datatable = QueryReport.prototype.render_datatable;
		QueryReport.prototype.render_datatable = function () {
			if (is_app_report(this)) {
				try {
					fit_columns(this);
				} catch (e) {
					// The report is still drawn with its own widths.
					console.error(e);
				}
			}
			return render_datatable.apply(this, arguments);
		};
		QueryReport.prototype.__ivri_od_column_width = true;
		return true;
	}

	// The report bundle defines QueryReport; wait for it if this script runs first.
	if (!patch_query_report()) {
		const timer = setInterval(() => {
			if (patch_query_report()) clearInterval(timer);
		}, 50);
		setTimeout(() => clearInterval(timer), 10000);
	}
})();
