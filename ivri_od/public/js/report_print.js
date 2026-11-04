// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// Print and Download buttons of the statement reports (Stock Account for Paddy, Rice Stock Report,
// New NBT Gunny Account): ivri_od.report_print.add_buttons(report).
// - Print: the report's statement layout (<report>.html) in a new tab, and the browser's print
//   dialog opens at once (Frappe's own Print only shows the page).
// - Download > PDF: the same layout as a PDF file; a failure is shown (Frappe's own says nothing).
// - Download > Excel / CSV: the rows left by the table's filters, Sl No 1, 2, 3... (report_export.py).
frappe.provide("ivri_od.report_print");

(function () {
	const PDF_METHOD = "/api/method/frappe.utils.print_format.report_to_pdf";
	const EXPORT_METHOD = "frappe.desk.query_report.export_query";

	function has_data(report) {
		if (!report.data?.length) {
			frappe.msgprint(__("Set the filters and run the report first"));
			return false;
		}
		return true;
	}

	// Full HTML page of the statement, as Frappe's report Print / PDF build it.
	function statement_html(report, orientation) {
		const title = __(report.report_name);
		const print_settings = { orientation };
		const columns = report.columns;
		const content = frappe.render_template(report.report_settings.html_format || "print_grid", {
			title,
			filters: report.get_filter_values(),
			data: report.get_data_for_print(),
			original_data: report.data,
			columns,
			report,
			print_settings,
		});
		return frappe.render_template("print_template", {
			title,
			content,
			base_url: frappe.urllib.get_base_url(),
			print_css: frappe.boot.print_css,
			print_settings,
			landscape: orientation === "Landscape",
			columns,
			lang: frappe.boot.lang,
			layout_direction: frappe.utils.is_rtl() ? "rtl" : "ltr",
			can_use_smaller_font: 0,
		});
	}

	// File name from the report and its filters, e.g. "New NBT Gunny Account_M051007_25-26.pdf".
	function file_name(report, extension) {
		const values = Object.values(report.get_filter_values() || {})
			.filter((value) => value && typeof value !== "object")
			.slice(0, 4);
		return `${[__(report.report_name), ...values].join("_").replace(/[\\/:*?"<>|]/g, "-")}.${extension}`;
	}

	function print_statement(report, orientation) {
		// Opened first, straight from the click, so the browser does not block the new tab.
		const win = window.open("", "_blank");
		if (!win) {
			frappe.msgprint(__("The browser blocked the print page. Allow pop-ups for this site, then press Print again."));
			return;
		}
		report.make_access_log("Print", "PDF");
		win.document.write(statement_html(report, orientation));
		win.document.close();
		let printed = false;
		const open_print_dialog = () => {
			if (printed) return;
			printed = true;
			win.focus();
			win.print();
		};
		// After the print styles have loaded; a slow load still gets the dialog.
		win.addEventListener("load", open_print_dialog);
		setTimeout(open_print_dialog, 2000);
	}

	function download_pdf(report, orientation) {
		report.make_access_log("Print", "PDF");
		const form = new FormData();
		form.append("html", statement_html(report, orientation));
		form.append("orientation", orientation);

		const xhr = new XMLHttpRequest();
		xhr.open("POST", PDF_METHOD);
		xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
		xhr.responseType = "arraybuffer";
		frappe.dom.freeze(__("Making PDF..."));
		xhr.onload = function () {
			frappe.dom.unfreeze();
			if (this.status !== 200) {
				show_pdf_error(this.response);
				return;
			}
			const url = URL.createObjectURL(new Blob([this.response], { type: "application/pdf" }));
			const link = document.createElement("a");
			link.href = url;
			link.download = file_name(report, "pdf");
			document.body.appendChild(link);
			link.click();
			link.remove();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
		};
		xhr.onerror = function () {
			frappe.dom.unfreeze();
			frappe.msgprint(__("The PDF could not be made: the server could not be reached."));
		};
		xhr.send(form);
	}

	function show_pdf_error(response) {
		let detail = "";
		try {
			const body = JSON.parse(new TextDecoder().decode(response));
			const messages = body._server_messages ? JSON.parse(body._server_messages) : [];
			detail = messages.map((m) => JSON.parse(m).message || m).join("<br>") || body.exception || "";
		} catch (e) {
			detail = "";
		}
		frappe.msgprint({
			title: __("PDF not made"),
			indicator: "red",
			message: `${__("The PDF could not be made. Try again; if it keeps failing, send this to support.")}${
				detail ? `<br><br><small>${frappe.utils.escape_html(String(detail).slice(0, 500))}</small>` : ""
			}`,
		});
	}

	function download_file(report, file_format) {
		report.make_access_log("Export", file_format);
		const filters = report.get_filter_values(true);
		// Rows left by the column filters of the table (total row excluded), as Frappe's Export sends them.
		const visible_idx = report.datatable?.bodyRenderer.visibleRowIndices || [];
		const all_rows = visible_idx.length === report.data.length - (report.raw_data?.add_total_row ? 1 : 0);
		open_url_post(frappe.request.url, {
			cmd: EXPORT_METHOD,
			report_name: report.report_name,
			custom_columns: [],
			file_format_type: file_format,
			filters,
			applied_filters: report.get_applied_filters(filters),
			visible_idx: all_rows ? [] : visible_idx,
			ignore_visible_idx: all_rows,
		});
	}

	ivri_od.report_print.add_buttons = function (report, { orientation = "Landscape" } = {}) {
		report.page.add_inner_button(__("Print"), () => {
			has_data(report) && print_statement(report, orientation);
		});
		const download = __("Download");
		report.page.add_inner_button(__("PDF"), () => has_data(report) && download_pdf(report, orientation), download);
		report.page.add_inner_button(__("Excel"), () => has_data(report) && download_file(report, "Excel"), download);
		report.page.add_inner_button(__("CSV"), () => has_data(report) && download_file(report, "CSV"), download);
	};
})();
