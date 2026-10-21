// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// Detail rows of a Portal Record (e.g. the lots of a DC) laid out as on the
// portal: same column order, the portal's header rows for groups such as
// "BRL Lot Details - Lot No." or "RECEIPT OF GUNNY (in Bags) - ROAD - C",
// and the portal's footer lines (e.g. "Total").
// Used by the Portal Record form, the SCMS section reports and the
// "Manual Entry" button of the RRC Detail from SCMS page.

frappe.provide("ivri_od.portal");

const PORTAL_TOTAL = /^(grand |sub ?)?total\s*:?$/i;

ivri_od.portal.detail_table_html = function (rows, footer) {
	footer = Array.isArray(footer) ? footer : [];
	if (!rows || !rows.length) {
		return `<p class="text-muted">${__("No detail rows")}</p>`;
	}
	const esc = frappe.utils.escape_html;
	const headers = [];
	[...rows, ...footer].forEach((r) => Object.keys(r).forEach((h) => !headers.includes(h) && headers.push(h)));
	const body_row = (r) => `<tr>${headers.map((h) => `<td>${esc(r[h] || "")}</td>`).join("")}</tr>`;
	return `
		<div style="overflow-x: auto">
			<table class="table table-bordered table-sm">
				<thead>${ivri_od.portal.header_rows(headers)}</thead>
				<tbody>${rows.map(body_row).join("")}</tbody>
				${footer.length ? `<tfoot style="font-weight: bold">${footer.map(body_row).join("")}</tfoot>` : ""}
			</table>
		</div>`;
};

// Header rows of a portal table. The agent joins the portal's merged header
// rows with " - " ("RECEIPT OF GUNNY (in Bags) - ROAD - C"); this splits them
// back: one row per level, a group cell over its columns, and a short header
// (e.g. "Date - A") spanning down to its last part. Returns rows of
// {text, colspan, rowspan}.
ivri_od.portal.header_levels = function (headers) {
	const parts = headers.map((h) => h.split(" - "));
	// Only a table with a real group (2+ columns under one name) has several header rows.
	const grouped = parts.some(
		(p, i) => p.length > 1 && i + 1 < parts.length && parts[i + 1].length > 1 && parts[i + 1][0] === p[0]
	);
	if (!grouped) {
		return [headers.map((text) => ({ text, colspan: 1, rowspan: 1 }))];
	}
	const depth = Math.max(...parts.map((p) => p.length));
	// [first part, gaps covered by its rowspan (null)..., remaining parts]
	const grid = parts.map((p) => [p[0], ...Array(depth - p.length).fill(null), ...p.slice(1)]);
	const levels = [];
	for (let level = 0; level < depth; level++) {
		const cells = [];
		for (let col = 0; col < grid.length; col++) {
			const text = grid[col][level];
			if (text === null) {
				continue; // covered by the cell above
			}
			let rowspan = 1;
			while (level + rowspan < depth && grid[col][level + rowspan] === null) {
				rowspan++;
			}
			const same_parent = (a, b) => grid[a].slice(0, level).every((t, i) => t === grid[b][i]);
			const last = cells[cells.length - 1];
			if (last && last.text === text && last.rowspan === rowspan && same_parent(last.col, col)) {
				last.colspan++;
			} else {
				cells.push({ text, colspan: 1, rowspan, col });
			}
		}
		levels.push(cells);
	}
	return levels;
};

ivri_od.portal.header_rows = function (headers, lead_label = null) {
	const esc = frappe.utils.escape_html;
	const levels = ivri_od.portal.header_levels(headers);
	return levels
		.map((cells, level) => {
			const lead = level === 0 && lead_label !== null ? `<th rowspan="${levels.length}">${esc(lead_label)}</th>` : "";
			const ths = cells.map(
				(c) =>
					`<th colspan="${c.colspan}" rowspan="${c.rowspan}" class="${c.colspan > 1 ? "text-center" : ""}">${esc(c.text)}</th>`
			);
			return `<tr>${lead}${ths.join("")}</tr>`;
		})
		.join("");
};

// Pop-up with the detail table of one Portal Record.
ivri_od.portal.show_details = function (record) {
	frappe
		.xcall("ivri_od.procurement.portal_report.get_record_details", {
			record,
		})
		.then((r) => {
			const dialog = new frappe.ui.Dialog({
				title: r.title,
				size: "extra-large",
				fields: [{ fieldtype: "HTML", fieldname: "details" }],
			});
			dialog.fields_dict.details.$wrapper.html(ivri_od.portal.detail_table_html(r.rows, r.footer));
			dialog.show();
		});
};

// Settings of an SCMS section report (procurement/portal_report.py).
// opts.details: "Show Detail Rows" filter (DC lots); opts.document_label: the
// column holding the PDF saved from the row's Action button (e.g. Challan);
// opts.print_documents: that column says "Print" and opens the PDF to print;
// opts.portal_layout: show the rows as the portal table (grouped headers,
// "Total" at the bottom) instead of the grid, with a "Grid View" filter to switch.
ivri_od.portal.section_report_settings = function (opts = {}) {
	const filters = [
		{ fieldname: "from_date", label: __("Seen From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("Seen To"), fieldtype: "Date" },
		{ fieldname: "search", label: __("Search Text"), fieldtype: "Data" },
		// Several mills, each with its own portal account: show one mill's rows.
		{ fieldname: "mill_id", label: __("Mill No."), fieldtype: "Link", options: "Mill Master" },
		{ fieldname: "entry_source", label: __("Entered From"), fieldtype: "Select", options: "\nPortal\nManual" },
	];
	if (opts.details) {
		filters.push({ fieldname: "show_details", label: __("Show Detail Rows (Lots)"), fieldtype: "Check" });
	}
	if (opts.portal_layout) {
		filters.push({ fieldname: "grid_view", label: __("Grid View"), fieldtype: "Check" });
	}
	return {
		filters,

		onload(report) {
			report.page.add_inner_button(__("Portal View"), () => ivri_od.portal.show_report_as_portal(report));
		},

		after_refresh(report) {
			if (opts.portal_layout) {
				ivri_od.portal.render_portal_layout(report);
			}
		},

		formatter(value, row, column, data, default_formatter) {
			const pdf = data && data.receipt;
			if (column.fieldname === "receipt") {
				if (!pdf) {
					return `<span class="text-muted">${__("Not saved")}</span>`;
				}
				// Print: open the PDF in a new tab, where the browser's Print button prints it.
				return opts.print_documents
					? `<a href="${encodeURI(pdf)}" target="_blank" rel="noopener">${__("Print")}</a>`
					: `<a href="${encodeURI(pdf)}" target="_blank" rel="noopener" download>${__("Download")}</a>`;
			}
			// Document columns (e.g. Details, AC Note Doc): the saved file of that button.
			if (/^doc\d+$/.test(column.fieldname)) {
				return value
					? `<a href="${encodeURI(value)}" target="_blank" rel="noopener">${__("Download")}</a>`
					: `<span class="text-muted">${__("Not saved")}</span>`;
			}
			let text = default_formatter(value, row, column, data);
			// Portal cell that held the document button (e.g. View DC: View_RRC): link to the saved file,
			// shown as opts.file_link_text (e.g. "Download_DC") when set.
			const file = data && data[`${column.fieldname}_file`];
			if (file) {
				const label = opts.file_link_text ? frappe.utils.escape_html(opts.file_link_text) : text;
				return `<a href="${encodeURI(file)}" target="_blank" rel="noopener">${label}</a>`;
			}
			if (column.fieldname === "entry_source" && value === "Manual") {
				return `<span class="indicator-pill orange">${text}</span>`;
			}
			if (data && ivri_od.portal.is_total_row(data)) {
				text = `<b>${text}</b>`;
			}
			// Key column (e.g. DC NO.): lots pop-up, or the saved document.
			if (column.opens_details && data && data.record && data.detail_count) {
				const record = frappe.utils.escape_html(data.record);
				return `<a href="#" onclick="ivri_od.portal.show_details('${record}'); return false;">${text}</a>`;
			}
			if (column.opens_details && opts.document_label && pdf) {
				return `<a href="${encodeURI(pdf)}" target="_blank" rel="noopener">${text}</a>`;
			}
			return text;
		},
	};
};

// A portal "Total" line (e.g. the last line of the Gunny Stock Register).
ivri_od.portal.is_total_row = function (row) {
	return Object.keys(row).some((k) => /^c\d+$/.test(k) && PORTAL_TOTAL.test(String(row[k] || "").trim()));
};

// Report rows as {portal column: value} maps, "Total" lines apart (footer).
ivri_od.portal.report_rows = function (report) {
	// Mill No. (first), portal columns, and columns worked out from them (e.g. Remaining Balance).
	const columns = (report.columns || []).filter((c) => /^([cx]\d+|mill_id)$/.test(c.fieldname || c.id));
	const rows = [];
	const footer = [];
	(report.data || []).forEach((d) => {
		const out = {};
		columns.forEach((c) => (out[c.label || c.name] = d[c.fieldname || c.id] || ""));
		(ivri_od.portal.is_total_row(d) ? footer : rows).push(out);
	});
	return { rows, footer };
};

// The report rows laid out like the portal table: same columns and order,
// grouped headers shown as on the portal.
ivri_od.portal.show_report_as_portal = function (report) {
	const { rows, footer } = ivri_od.portal.report_rows(report);
	const dialog = new frappe.ui.Dialog({
		title: report.report_name,
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "table" }],
	});
	dialog.fields_dict.table.$wrapper.html(ivri_od.portal.detail_table_html(rows, footer));
	dialog.show();
};

// Portal table in place of the report grid (opts.portal_layout); "Grid View" shows the grid.
ivri_od.portal.render_portal_layout = function (report) {
	report.page.main.find(".portal-layout").remove();
	if (!(report.data || []).length) {
		return;
	}
	if (report.get_filter_value("grid_view")) {
		report.$report.show();
		return;
	}
	const { rows, footer } = ivri_od.portal.report_rows(report);
	report.$report.hide();
	$(`<div class="portal-layout" style="max-height: 70vh; overflow: auto"></div>`)
		.html(ivri_od.portal.detail_table_html(rows, footer))
		.insertAfter(report.$report);
};

// ---------------------------------------------------------------
// Manual entry (procurement/portal_manual.py)
// ---------------------------------------------------------------

const PORTAL_MANUAL = "ivri_od.procurement.portal_manual";
const MANUAL_START_ROWS = 15;

// Entries of the "Manual Entry" drop-down: [{form, label}].
ivri_od.portal.get_manual_forms = function (group = "rrc") {
	return frappe.xcall(`${PORTAL_MANUAL}.get_manual_forms`, { group });
};

// Excel-like grid of the form's columns: type, or paste rows copied from Excel.
ivri_od.portal.open_manual_entry = async function (form) {
	const config = await frappe.xcall(`${PORTAL_MANUAL}.get_manual_form`, { form });
	const fields = [];
	if (config.lots) {
		// The parent row of the detail rows: a DC (its lots), a TEC (its Delivered lines).
		fields.push({
			fieldname: "dc_no",
			label: config.parent_label,
			fieldtype: "Autocomplete",
			reqd: 1,
			// Keep a typed DC NO. that is not in the list: the server says if the DC is missing.
			ignore_validation: 1,
			description: __("Pick the {0} first, then paste all its detail rows below.", [config.parent_label]),
		});
	}
	if (!config.lots) {
		fields.push({
			fieldname: "mill_id",
			label: __("Mill No."),
			fieldtype: "Link",
			options: "Mill Master",
			reqd: 1,
			default: config.mill_id,
			get_query: () => ({ filters: { is_active: 1 } }),
			description: __("The mill these rows belong to."),
		});
		if (config.common_fields.length) {
			fields.push({ fieldtype: "Column Break" });
		}
	}
	config.common_fields.forEach((name, idx) => {
		if (idx) {
			fields.push({ fieldtype: "Column Break" });
		}
		fields.push({
			fieldname: `common_${idx}`,
			label: __(name),
			fieldtype: "Data",
			description: __("Saved with every row below."),
		});
	});
	fields.push(
		{ fieldtype: "Section Break" },
		{
			fieldname: "help",
			fieldtype: "HTML",
			options: `<p class="text-muted small">${__(
				"Copy rows in Excel (or from the portal) and press Ctrl+V in the first cell. Must fill: {0}. A row read from the portal is never replaced here: portal data has priority.",
				[(config.lots ? [config.parent_label] : config.key_columns).join(", ")]
			)}</p>`,
		},
		{ fieldname: "grid", fieldtype: "HTML" }
	);

	const dialog = new frappe.ui.Dialog({
		title: __("Manual Entry: {0}", [config.label]),
		size: "extra-large",
		fields,
		primary_action_label: __("Save"),
		primary_action: () => ivri_od.portal.save_manual_entry(dialog, config, grid),
		secondary_action_label: __("Add 10 Rows"),
		secondary_action: () => grid.add_rows(10),
	});
	if (config.lots) {
		// The Autocomplete reads its list from the server on each key press.
		const field = dialog.fields_dict.dc_no;
		field.$input.on("input", frappe.utils.debounce(() => ivri_od.portal.load_parent_rows(field, config.form), 300));
		ivri_od.portal.load_parent_rows(field, config.form);
	}
	const grid = new ivri_od.portal.ManualGrid(dialog.fields_dict.grid.$wrapper, config.columns);
	dialog.show();
};

// [{label, value}]: DC NO.s, or the TECs by their summary (value = record).
ivri_od.portal.load_parent_rows = function (field, form) {
	frappe.xcall(`${PORTAL_MANUAL}.get_parent_rows`, { form, txt: field.get_input_value() || "" }).then((list) => {
		field.set_data(list || []);
	});
};

ivri_od.portal.save_manual_entry = async function (dialog, config, grid) {
	const rows = grid.get_rows();
	if (!rows.length) {
		frappe.msgprint(__("Paste or type at least one row."));
		return;
	}
	dialog.disable_primary_action();
	try {
		if (config.lots) {
			const parent = (dialog.get_value("dc_no") || "").trim();
			if (!parent) {
				frappe.msgprint(__("Enter the {0} first.", [config.parent_label]));
				return;
			}
			const r = await frappe.xcall(`${PORTAL_MANUAL}.save_manual_lots`, { form: config.form, parent, rows });
			frappe.show_alert({
				message: __("{0} detail row(s) saved for {1} {2}", [r.lots, config.parent_label, r.parent]),
				indicator: "green",
			});
			dialog.hide();
			return;
		}
		const common = {};
		config.common_fields.forEach((name, idx) => (common[name] = dialog.get_value(`common_${idx}`) || ""));
		const r = await frappe.xcall(`${PORTAL_MANUAL}.save_manual_rows`, {
			form: config.form,
			rows,
			common,
			mill_id: dialog.get_value("mill_id") || "",
		});
		const message = __("{0} new, {1} updated, {2} not saved.", [r.inserted, r.updated, r.errors.length]);
		if (r.errors.length) {
			frappe.msgprint({
				title: __("Some rows were not saved"),
				indicator: "orange",
				message: `${message}<ul>${r.errors.map((e) => `<li>${frappe.utils.escape_html(e)}</li>`).join("")}</ul>`,
			});
		} else {
			frappe.show_alert({ message, indicator: "green" });
			dialog.hide();
		}
	} finally {
		dialog.enable_primary_action();
	}
};

// Plain table of text boxes with the portal's header rows. Ctrl+V of cells
// copied from Excel (tab between columns, new line between rows) fills the
// grid from the selected cell, adding rows as needed.
ivri_od.portal.ManualGrid = class ManualGrid {
	constructor($wrapper, columns) {
		this.columns = columns;
		this.$table = $(`
			<div style="max-height: 60vh; overflow: auto">
				<table class="table table-bordered table-sm portal-manual-grid" style="font-size: 12px">
					<thead>${ivri_od.portal.header_rows(columns, "#")}</thead>
					<tbody></tbody>
				</table>
			</div>`).appendTo($wrapper.empty());
		this.$body = this.$table.find("tbody");
		this.add_rows(MANUAL_START_ROWS);
		this.$body.on("paste", "input", (e) => this.paste(e));
	}

	add_rows(count) {
		for (let i = 0; i < count; i++) {
			const no = this.$body.children().length + 1;
			const cells = this.columns.map(
				(c, idx) =>
					`<td style="padding: 0"><input type="text" data-col="${idx}" title="${frappe.utils.escape_html(c)}"
						style="border: 0; width: 100%; min-width: 90px; padding: 2px 4px"></td>`
			);
			this.$body.append(`<tr><td class="text-muted">${no}</td>${cells.join("")}</tr>`);
		}
	}

	paste(e) {
		const text = (e.originalEvent.clipboardData || window.clipboardData).getData("text");
		if (!text || (!text.includes("\t") && !text.includes("\n"))) {
			return; // one value: normal paste
		}
		e.preventDefault();
		const lines = text.replace(/\r/g, "").replace(/\n+$/, "").split("\n");
		const $input = $(e.target);
		const start_col = cint($input.attr("data-col"));
		let row_index = $input.closest("tr").index();
		lines.forEach((line) => {
			while (row_index >= this.$body.children().length) {
				this.add_rows(10);
			}
			const $inputs = this.$body.children().eq(row_index).find("input");
			line.split("\t").forEach((value, offset) => {
				const col = start_col + offset;
				if (col < this.columns.length) {
					$inputs.eq(col).val(value.trim());
				}
			});
			row_index++;
		});
	}

	// Non-empty rows as {column: value}, without the portal's header line if it was pasted too.
	get_rows() {
		const rows = [];
		this.$body.children().each((_i, tr) => {
			const row = {};
			let filled = false;
			let header_line = true;
			$(tr)
				.find("input")
				.each((idx, input) => {
					const value = (input.value || "").trim();
					row[this.columns[idx]] = value;
					filled = filled || !!value;
					header_line = header_line && (!value || this.columns[idx].endsWith(value));
				});
			if (filled && !header_line) {
				rows.push(row);
			}
		});
		return rows;
	}
};

// Button + drop-down of the RRC Detail from SCMS and DCRO Details pages (Custom
// HTML Blocks "RRC Manual Entry" / "DCRO Manual Entry", made by
// procurement_workspace._apply_portal_workspace). ``group``: whose forms to list.
ivri_od.portal.setup_manual_entry_block = function (root, group = "rrc") {
	const button = root.querySelector(".manual-entry-button");
	const menu = root.querySelector(".manual-entry-menu");
	if (!button || !menu) {
		return;
	}
	button.addEventListener("click", async () => {
		if (menu.style.display === "block") {
			menu.style.display = "none";
			return;
		}
		const forms = await ivri_od.portal.get_manual_forms(group);
		menu.innerHTML = "";
		forms.forEach((f) => {
			const item = document.createElement("a");
			item.href = "#";
			item.className = "dropdown-item";
			item.textContent = f.label;
			item.addEventListener("click", (e) => {
				e.preventDefault();
				menu.style.display = "none";
				ivri_od.portal.open_manual_entry(f.form);
			});
			menu.appendChild(item);
		});
		menu.style.display = "block";
	});
};
