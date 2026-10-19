// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Mandi Book"] = {
	collapsible_filters: true,
	filters: [
		{
			fieldname: "season",
			label: __("Season"),
			fieldtype: "Link",
			options: "Season Master",
		},
		{
			fieldname: "mill_name",
			label: __("Mill Name (Code)"),
			fieldtype: "Link",
			options: "Mill Master",
		},
		{
			fieldname: "ppc_name",
			label: __("PPC Name"),
			fieldtype: "Link",
			options: "PPC Master",
		},
		{
			fieldname: "transit_pass_no",
			label: __("TP No"),
			fieldtype: "Data",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const fieldname = (column && (column.fieldname || column.id)) || "";
		if (data && data.pass_unique_key) {
			window.__mandi_book_rows = window.__mandi_book_rows || {};
			window.__mandi_book_rows[data.pass_unique_key] = data;
		}

		if (value == null || value === "") {
			return "";
		}

		if (fieldname === "grn_count" || fieldname === "rst_count" || fieldname === "entry_count") {
			return `<span class="text-muted font-weight-bold">${frappe.utils.escape_html(String(value))}</span>`;
		}

		if (fieldname === "detail_type") {
			if (value === "GRN") {
				return `<span class="indicator-pill green">${__("GRN")}</span>`;
			}
			if (value === "Entry") {
				return `<span class="indicator-pill blue">${__("Entry")}</span>`;
			}
			if (value === "GRN & Entry") {
				return `<span class="indicator-pill green">${__("GRN")}</span> <span class="indicator-pill blue">${__("Entry")}</span>`;
			}
			return `<span class="indicator-pill gray">${frappe.utils.escape_html(value)}</span>`;
		}

		if (fieldname === "grn_no") {
			const docname = (data && data.grn_name) || value;
			const link = frappe.utils.get_form_link("GRN Note", docname);
			return `<a href="${link}">${frappe.utils.escape_html(value)}</a>`;
		}

		if (fieldname === "rst_no") {
			if (data && data.weigh_bridge_measurement) {
				const link = frappe.utils.get_form_link("Weigh Bridge Measurement", data.weigh_bridge_measurement);
				return `<a href="${link}">${frappe.utils.escape_html(value)}</a>`;
			}
			return frappe.utils.escape_html(value);
		}

		if (fieldname === "entry") {
			const link = frappe.utils.get_form_link("Entry", value);
			return `<a href="${link}">${frappe.utils.escape_html(value)}</a>`;
		}

		if (fieldname === "chhatni_status") {
			return mandi_book_status_pill(value);
		}

		if (fieldname === "tp_status") {
			const indicator = value === __("TP Completed") ? "green" : (value === __("Pending") ? "gray" : "orange");
			return `<span class="indicator-pill ${indicator}">${frappe.utils.escape_html(value)}</span>`;
		}

		return default_formatter(value, row, column, data);
	},
	after_datatable_render(datatable) {
		apply_mandi_book_grouping(datatable);
		render_mandi_book_super_header(datatable);
	},
	show_popup(kind, data) {
		mandi_book_dialog(kind, data || {});
	},
};

function apply_mandi_book_grouping(datatable) {
	if (!datatable || !datatable.datamanager) {
		return;
	}

	const rows = datatable.datamanager.data || [];
	const totalRows = rows.length;
	const viewOrder =
		datatable.datamanager.rowViewOrder && datatable.datamanager.rowViewOrder.length === totalRows
			? datatable.datamanager.rowViewOrder
			: Array.from({ length: totalRows }, (_, i) => i);

	let current_tp = 0;
	const tp_sr_map = {};
	const group_end_indices = [];

	for (let v = 0; v < viewOrder.length; v++) {
		const rowIndex = viewOrder[v];
		const d = datatable.datamanager.getData(rowIndex);
		const isFirstRow = Boolean(d && (d.pass_unique_key || d.transit_pass_no));
		if (isFirstRow) {
			current_tp += 1;
			tp_sr_map[rowIndex] = String(current_tp);
		} else {
			tp_sr_map[rowIndex] = "";
		}

		const nextRowIndex = viewOrder[v + 1];
		const next_d = nextRowIndex != null ? datatable.datamanager.getData(nextRowIndex) : null;
		const isLastRowOfGroup =
			v === viewOrder.length - 1 || Boolean(next_d && (next_d.pass_unique_key || next_d.transit_pass_no));
		if (isLastRowOfGroup) {
			group_end_indices.push(rowIndex);
		}
	}

	const srNoColIndex = datatable.datamanager.getColumnIndexById("_rowIndex");
	const srNoCol = datatable.datamanager.getColumnById("_rowIndex");

	if (srNoCol) {
		srNoCol.format = (value, row, column, data) => {
			const rowIndex =
				row && row.meta && row.meta.rowIndex != null
					? row.meta.rowIndex
					: row && row[0] && row[0].rowIndex != null
					? row[0].rowIndex
					: data && data.rowIndex != null
					? data.rowIndex
					: null;
			if (rowIndex != null && tp_sr_map[rowIndex] !== undefined) {
				return tp_sr_map[rowIndex];
			}
			if (data && (data.pass_unique_key || data.transit_pass_no)) {
				return value || "";
			}
			return "";
		};
	}

	if (srNoColIndex >= 0 && datatable.datamanager.rows) {
		datatable.datamanager.rows.forEach((row, i) => {
			const cell = row[srNoColIndex];
			if (cell) {
				const val = tp_sr_map[i] != null ? tp_sr_map[i] : "";
				cell.content = val;
				cell.html = val;
			}
		});
	}

	const columns = (datatable && datatable.datamanager && typeof datatable.datamanager.getColumns === "function")
		? datatable.datamanager.getColumns()
		: [];
	const summaryColIndices = [];
	const entryColIndices = [];
	const grnColIndices = [];
	let rowIndexColIndex = -1;
	let grnColIndex = -1;
	let entryColIndex = -1;
	let lastGrnColIndex = -1;

	const summaryFieldnames = new Set([
		"season",
		"ppc_name",
		"mill_name",
		"transit_pass_no",
		"pass_unique_key",
		"tp_quantity",
		"total_gross_weight",
		"summary_gunny_type",
		"total_gunny_weight",
		"total_deduction_received",
		"total_received",
		"pending_qty",
		"excess_received_qty",
		"tp_status",
		"jute_pkt",
		"plastic_pkt",
		"total_bags",
		"chhatni_assigned",
		"actual_chhatni_pct",
		"chhatni_status"
	]);

	const entryFieldnames = new Set([
		"entry",
		"agent_name",
		"entry_quantity",
		"entry_price_per_quintal",
		"total_amount"
	]);

	const grnFieldnames = new Set([
		"grn_no",
		"rst_no",
		"vehicle_no",
		"load_weight",
		"tare_weight",
		"gross_weight",
		"gunny_type",
		"gunny_weight",
		"deduction",
		"net_weight"
	]);

	columns.forEach((c) => {
		const fn = c.id || c.fieldname || "";
		const idx = c.colIndex != null ? c.colIndex : -1;
		if (idx < 0) return;

		if (fn === "_rowIndex") {
			rowIndexColIndex = idx;
		} else if (summaryFieldnames.has(fn)) {
			summaryColIndices.push(idx);
		} else if (entryFieldnames.has(fn)) {
			entryColIndices.push(idx);
			if (fn === "entry") entryColIndex = idx;
		} else if (grnFieldnames.has(fn)) {
			grnColIndices.push(idx);
			if (fn === "grn_no") grnColIndex = idx;
			if (fn === "net_weight") lastGrnColIndex = idx;
		}
	});

	if (grnColIndex < 0 && typeof datatable.datamanager.getColumnIndexById === "function") {
		grnColIndex = datatable.datamanager.getColumnIndexById("grn_no");
	}
	if (entryColIndex < 0 && typeof datatable.datamanager.getColumnIndexById === "function") {
		entryColIndex = datatable.datamanager.getColumnIndexById("entry");
	}
	if (rowIndexColIndex < 0 && typeof datatable.datamanager.getColumnIndexById === "function") {
		rowIndexColIndex = datatable.datamanager.getColumnIndexById("_rowIndex");
	}
	if (lastGrnColIndex < 0 && typeof datatable.datamanager.getColumnIndexById === "function") {
		lastGrnColIndex = datatable.datamanager.getColumnIndexById("net_weight");
	}

	const lastSummaryColIndex = summaryColIndices.length ? Math.max(...summaryColIndices) : -1;
	const lastEntryColIndex = entryColIndices.length ? Math.max(...entryColIndices) : -1;

	inject_mandi_book_styles(group_end_indices, {
		grnColIndex,
		entryColIndex,
		rowIndexColIndex,
		lastSummaryColIndex,
		lastEntryColIndex,
		lastGrnColIndex,
		summaryColIndices,
		entryColIndices,
		grnColIndices
	});

	if (datatable.wrapper) {
		const oldEnds = datatable.wrapper.querySelectorAll(".mandi-book-group-end");
		if (oldEnds) {
			oldEnds.forEach((el) => el.classList.remove("mandi-book-group-end"));
		}
		group_end_indices.forEach((idx) => {
			const $row = datatable.wrapper.querySelector(`.dt-row-${idx}`);
			if ($row) {
				$row.classList.add("mandi-book-group-end");
			}
		});
	}

	if (!datatable._applying_mandi_grouping && datatable.renderBody) {
		try {
			datatable._applying_mandi_grouping = true;
			datatable.renderBody();
		} finally {
			datatable._applying_mandi_grouping = false;
		}
	}

	if (!datatable._mandi_sort_listener_attached && datatable.on) {
		datatable._mandi_sort_listener_attached = true;
		datatable.on("onSortColumn", () => {
			apply_mandi_book_grouping(datatable);
		});
		datatable.on("onSwitchColumn", () => {
			apply_mandi_book_grouping(datatable);
		});
	}
}

function inject_mandi_book_styles(group_end_indices, col_indices = {}) {
	let style = document.getElementById("mandi-book-group-styles");
	if (!style) {
		style = document.createElement("style");
		style.id = "mandi-book-group-styles";
		document.head.appendChild(style);
	}

	let group_border_css = "";
	if (group_end_indices && group_end_indices.length > 0) {
		const selectors = group_end_indices
			.map((idx) => `.report-wrapper .dt-row-${idx} .dt-cell, .datatable .dt-row-${idx} .dt-cell`)
			.join(",\n\t\t");
		group_border_css = `
		.report-wrapper .mandi-book-group-end .dt-cell,
		.datatable .mandi-book-group-end .dt-cell,
		${selectors} {
			border-bottom: 2px solid var(--gray-600, #4c5a67) !important;
		}
		`;
	}

	let vertical_border_css = "";
	const rowIndexCol = col_indices.rowIndexColIndex != null ? col_indices.rowIndexColIndex : -1;
	const lastSummaryCol = col_indices.lastSummaryColIndex != null ? col_indices.lastSummaryColIndex : -1;
	const lastEntryCol = col_indices.lastEntryColIndex != null ? col_indices.lastEntryColIndex : -1;
	const lastGrnCol = col_indices.lastGrnColIndex != null ? col_indices.lastGrnColIndex : -1;

	if (rowIndexCol >= 0) {
		vertical_border_css += `
		.report-wrapper .dt-cell--col-${rowIndexCol},
		.datatable .dt-cell--col-${rowIndexCol} {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		`;
	}

	if (lastSummaryCol >= 0) {
		vertical_border_css += `
		.report-wrapper .dt-cell--col-${lastSummaryCol},
		.datatable .dt-cell--col-${lastSummaryCol} {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		`;
	}

	if (lastEntryCol >= 0) {
		vertical_border_css += `
		.report-wrapper .dt-cell--col-${lastEntryCol},
		.datatable .dt-cell--col-${lastEntryCol} {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		`;
	}

	if (lastGrnCol >= 0) {
		vertical_border_css += `
		.report-wrapper .dt-cell--col-${lastGrnCol},
		.datatable .dt-cell--col-${lastGrnCol} {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		`;
	}

	let section_header_colors_css = "";
	const summaryCols = col_indices.summaryColIndices || [];
	const entryCols = col_indices.entryColIndices || [];
	const grnCols = col_indices.grnColIndices || [];

	if (summaryCols.length > 0) {
		const sel = summaryCols
			.map((i) => `.report-wrapper .dt-header .dt-cell--col-${i}, .report-wrapper .dt-header .dt-cell--col-${i} .dt-cell__content`)
			.join(",\n\t\t");
		section_header_colors_css += `
		${sel} {
			background-color: #eff6ff !important;
			color: #1e293b !important;
		}
		`;
	}

	if (entryCols.length > 0) {
		const sel = entryCols
			.map((i) => `.report-wrapper .dt-header .dt-cell--col-${i}, .report-wrapper .dt-header .dt-cell--col-${i} .dt-cell__content`)
			.join(",\n\t\t");
		section_header_colors_css += `
		${sel} {
			background-color: #f0fdf4 !important;
			color: #1e293b !important;
		}
		`;
	}

	if (grnCols.length > 0) {
		const sel = grnCols
			.map((i) => `.report-wrapper .dt-header .dt-cell--col-${i}, .report-wrapper .dt-header .dt-cell--col-${i} .dt-cell__content`)
			.join(",\n\t\t");
		section_header_colors_css += `
		${sel} {
			background-color: #fffbeb !important;
			color: #1e293b !important;
		}
		`;
	}

	if (rowIndexCol >= 0) {
		section_header_colors_css += `
		.report-wrapper .dt-header .dt-cell--col-${rowIndexCol},
		.report-wrapper .dt-header .dt-cell--col-${rowIndexCol} .dt-cell__content {
			background-color: #f8fafc !important;
			color: #64748b !important;
		}
		`;
	}

	style.textContent = `
		.report-wrapper .dt-cell--col-0,
		.datatable .dt-cell--col-0 {
			font-weight: 600;
		}
		.dt-row-super-header {
			display: flex;
			background-color: var(--dt-header-cell-bg, #f1f5f9);
			border-bottom: 2px solid var(--gray-600, #4c5a67) !important;
			min-height: 42px;
			box-sizing: border-box;
			width: max-content;
			min-width: 100%;
			margin: 0;
			padding: 0;
		}
		.dt-super-cell {
			border: 1px solid var(--dt-border-color, #cbd5e1);
			border-bottom: none !important;
			border-left: none;
			padding: 6px 10px;
			text-align: center;
			box-sizing: border-box;
			display: flex;
			flex-direction: column;
			justify-content: center;
			align-items: center;
			overflow: hidden;
			flex-shrink: 0;
			margin: 0;
		}
		.dt-super-cell:first-child {
			border-left: 1px solid var(--dt-border-color, #cbd5e1);
		}
		.dt-super-cell--spacer {
			background-color: #f1f5f9 !important;
			font-weight: 700;
			font-size: 12px;
			color: #475569 !important;
		}
		.dt-super-cell--row-index-divider {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		.dt-super-cell--summary {
			background-color: #dbeafe !important;
			color: #1e3a8a !important;
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		.dt-super-cell--entry {
			background-color: #dcfce7 !important;
			color: #14532d !important;
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		.dt-super-cell--grn {
			background-color: #fef3c7 !important;
			color: #78350f !important;
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		.dt-super-cell-title {
			font-size: 13px;
			font-weight: 700;
			line-height: 1.3;
			letter-spacing: 0.5px;
			text-transform: uppercase;
			white-space: normal;
			word-wrap: break-word;
			overflow-wrap: break-word;
			text-align: center;
			width: 100%;
			max-width: 100%;
		}
		.report-wrapper .dt-row-header,
		.datatable .dt-row-header {
			border-top: none !important;
			margin: 0;
			padding: 0;
			height: auto !important;
			min-height: 38px !important;
		}
		.report-wrapper .dt-row-header .dt-cell--header,
		.datatable .dt-row-header .dt-cell--header {
			border-top: none !important;
			height: auto !important;
			min-height: 38px !important;
			display: flex !important;
			align-items: center !important;
		}
		.report-wrapper .dt-header .dt-cell--header .dt-cell__content {
			white-space: normal !important;
			word-break: normal !important;
			overflow-wrap: break-word !important;
			text-overflow: unset !important;
			line-height: 1.25 !important;
			font-size: 12px !important;
			font-weight: 600 !important;
			padding: 4px 10px 4px 6px !important;
			display: flex !important;
			align-items: center !important;
			height: 100% !important;
		}
		.report-wrapper .dt-header .dt-cell--header .dt-dropdown {
			position: absolute !important;
			right: 4px !important;
			top: 50% !important;
			transform: translateY(-50%) !important;
		}
		${group_border_css}
		${vertical_border_css}
		${section_header_colors_css}
	`;
}

function render_mandi_book_super_header(datatable_obj) {
	if (!datatable_obj || !datatable_obj.header || !datatable_obj.datamanager) return;
	if (datatable_obj._super_header_rendering) return;

	const $ = window.jQuery || (typeof jQuery !== "undefined" ? jQuery : null);
	if (!$) return;

	const $headerRow = $(datatable_obj.header).find(".dt-row-header");
	if (!$headerRow.length) return;

	const columns = datatable_obj.datamanager.getColumns();
	if (!columns || !columns.length) return;

	datatable_obj._super_header_rendering = true;
	try {
		let $superHeader = $(datatable_obj.header).find(".dt-row-super-header");
		if (!$superHeader.length) {
			$superHeader = $('<div class="dt-row dt-row-super-header"></div>');
			$headerRow.before($superHeader);
		}
		$superHeader.empty();

		const getHeaderCell = (col) => {
			if (!col) return null;
			const colIndex = col.colIndex != null ? col.colIndex : -1;
			if (colIndex < 0) return null;
			return (
				$headerRow.find(`.dt-cell--col-${colIndex}`)[0] ||
				$headerRow.find(`.dt-cell--header-${colIndex}`)[0]
			);
		};

		const getGroupWidth = (startCol, endCol, fallbackSum) => {
			const startEl = getHeaderCell(startCol);
			const endEl = getHeaderCell(endCol);
			if (startEl && endEl && endEl.offsetWidth > 0) {
				const startLeft = startEl.offsetLeft;
				const endRight = endEl.offsetLeft + endEl.offsetWidth;
				const measuredWidth = endRight - startLeft;
				if (measuredWidth > 0) {
					return measuredWidth;
				}
			}
			return fallbackSum;
		};

		const getColWidth = (col) => {
			if (!col) return 0;
			const cellEl = getHeaderCell(col);
			if (cellEl && cellEl.offsetWidth > 0) {
				return cellEl.offsetWidth;
			}
			const baseW = parseFloat(col.width) || 120;
			return col.colIndex === 0 ? baseW + 2 : baseW + 1;
		};

		const toPx = (val) => `${Number(val).toFixed(2)}px`;

		const lastCol = columns[columns.length - 1];
		const lastCellEl = getHeaderCell(lastCol);
		let totalRowWidth = 0;
		if (lastCellEl && lastCellEl.offsetWidth > 0) {
			totalRowWidth = lastCellEl.offsetLeft + lastCellEl.offsetWidth;
		} else if ($headerRow[0]) {
			totalRowWidth = $headerRow[0].scrollWidth || $headerRow.outerWidth();
		}
		if (totalRowWidth > 0) {
			$superHeader.css({
				"width": totalRowWidth + "px",
				"min-width": totalRowWidth + "px",
				"max-width": totalRowWidth + "px"
			});
		}

		const summaryFieldnames = new Set([
			"season",
			"ppc_name",
			"mill_name",
			"transit_pass_no",
			"pass_unique_key",
			"tp_quantity",
			"total_gross_weight",
			"summary_gunny_type",
			"total_gunny_weight",
			"total_deduction_received",
			"total_received",
			"pending_qty",
			"excess_received_qty",
			"tp_status",
			"jute_pkt",
			"plastic_pkt",
			"total_bags",
			"chhatni_assigned",
			"actual_chhatni_pct",
			"chhatni_status"
		]);

		const entryFieldnames = new Set([
			"entry",
			"agent_name",
			"entry_quantity",
			"entry_price_per_quintal",
			"total_amount"
		]);

		const grnFieldnames = new Set([
			"grn_no",
			"rst_no",
			"vehicle_no",
			"load_weight",
			"tare_weight",
			"gross_weight",
			"gunny_type",
			"gunny_weight",
			"deduction",
			"net_weight"
		]);

		let i = 0;
		while (i < columns.length) {
			const col = columns[i];
			const fieldname = col.id || col.fieldname || "";

			if (fieldname === "_rowIndex") {
				const width = getColWidth(col);
				const $cell = $(`
					<div class="dt-super-cell dt-super-cell--spacer dt-super-cell--row-index-divider"
						style="width: ${toPx(width)}; min-width: ${toPx(width)}; max-width: ${toPx(width)}; flex: 0 0 ${toPx(width)};">
						<div class="dt-super-cell-title">#</div>
					</div>
				`);
				$superHeader.append($cell);
				i++;
			} else if (summaryFieldnames.has(fieldname)) {
				let startCol = null;
				let endCol = null;
				let fallbackSum = 0;

				while (i < columns.length && summaryFieldnames.has(columns[i].id || columns[i].fieldname || "")) {
					const c = columns[i];
					if (!c.hidden) {
						if (!startCol) startCol = c;
						endCol = c;
						fallbackSum += (parseFloat(c.width) || 120) + 1;
					}
					i++;
				}

				const totalWidth = getGroupWidth(startCol, endCol, fallbackSum);
				const $cell = $(`
					<div class="dt-super-cell dt-super-cell--summary" title="${__("Summary")}"
						style="width: ${toPx(totalWidth)}; min-width: ${toPx(totalWidth)}; max-width: ${toPx(totalWidth)}; flex: 0 0 ${toPx(totalWidth)};">
						<div class="dt-super-cell-title">${__("Summary")}</div>
					</div>
				`);
				$superHeader.append($cell);
			} else if (entryFieldnames.has(fieldname)) {
				let startCol = null;
				let endCol = null;
				let fallbackSum = 0;

				while (i < columns.length && entryFieldnames.has(columns[i].id || columns[i].fieldname || "")) {
					const c = columns[i];
					if (!c.hidden) {
						if (!startCol) startCol = c;
						endCol = c;
						fallbackSum += (parseFloat(c.width) || 120) + 1;
					}
					i++;
				}

				const totalWidth = getGroupWidth(startCol, endCol, fallbackSum);
				const $cell = $(`
					<div class="dt-super-cell dt-super-cell--entry" title="${__("Entry Details")}"
						style="width: ${toPx(totalWidth)}; min-width: ${toPx(totalWidth)}; max-width: ${toPx(totalWidth)}; flex: 0 0 ${toPx(totalWidth)};">
						<div class="dt-super-cell-title">${__("Entry Details")}</div>
					</div>
				`);
				$superHeader.append($cell);
			} else if (grnFieldnames.has(fieldname)) {
				let startCol = null;
				let endCol = null;
				let fallbackSum = 0;

				while (i < columns.length && grnFieldnames.has(columns[i].id || columns[i].fieldname || "")) {
					const c = columns[i];
					if (!c.hidden) {
						if (!startCol) startCol = c;
						endCol = c;
						fallbackSum += (parseFloat(c.width) || 120) + 1;
					}
					i++;
				}

				const totalWidth = getGroupWidth(startCol, endCol, fallbackSum);
				const $cell = $(`
					<div class="dt-super-cell dt-super-cell--grn" title="${__("GRN Details")}"
						style="width: ${toPx(totalWidth)}; min-width: ${toPx(totalWidth)}; max-width: ${toPx(totalWidth)}; flex: 0 0 ${toPx(totalWidth)};">
						<div class="dt-super-cell-title">${__("GRN Details")}</div>
					</div>
				`);
				$superHeader.append($cell);
			} else {
				const width = getColWidth(col);
				const $cell = $(`
					<div class="dt-super-cell dt-super-cell--spacer"
						style="width: ${toPx(width)}; min-width: ${toPx(width)}; max-width: ${toPx(width)}; flex: 0 0 ${toPx(width)};"></div>
				`);
				$superHeader.append($cell);
				i++;
			}
		}
	} finally {
		datatable_obj._super_header_rendering = false;
	}

	if (!datatable_obj.__mandi_header_bound) {
		datatable_obj.__mandi_header_bound = true;
		$(window).off("resize.mandi_book").on("resize.mandi_book", () => {
			render_mandi_book_super_header(datatable_obj);
		});
	}
	if (!datatable_obj.__mandi_resize_observer && typeof ResizeObserver !== "undefined" && $headerRow[0]) {
		const ro = new ResizeObserver(() => {
			render_mandi_book_super_header(datatable_obj);
		});
		ro.observe($headerRow[0]);
		datatable_obj.__mandi_resize_observer = ro;
	}
	if (!datatable_obj.__mandi_events_bound && datatable_obj.on) {
		datatable_obj.__mandi_events_bound = true;
		datatable_obj.on("onSortColumn", () => render_mandi_book_super_header(datatable_obj));
		datatable_obj.on("onSwitchColumn", () => render_mandi_book_super_header(datatable_obj));
	}
}

function mandi_book_status_pill(value) {
	const text = value == null || value === "" ? "" : String(value);
	let indicator = "gray";
	if (text === "Chhatni Received") {
		indicator = "green";
	} else if (text === "Extra Chhatni Received" || text === "Over Filled Chhatni Received") {
		indicator = "blue";
	} else if (text === "Chhatni Not Received") {
		indicator = "orange";
	} else if (text === "Chhatni Pending") {
		indicator = "yellow";
	}
	return `<span class="indicator-pill ${indicator}">${frappe.utils.escape_html(text)}</span>`;
}

function mandi_book_dialog(kind, data) {
	const is_grn = kind === "grn" || kind === "rst";
	const lines = is_grn ? (data.grn_lines || data.rst_lines || []) : (data.entry_lines || []);
	const tp_no = data.transit_pass_no || "";
	const title = is_grn ? __("GRN Details — TP {0}", [tp_no]) : __("Entry Details — TP {0}", [tp_no]);
	const dialog = new frappe.ui.Dialog({
		title,
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "details" }],
	});
	dialog.fields_dict.details.$wrapper.html(mandi_book_table(kind, lines));
	dialog.show();
}

function mandi_book_table(kind, lines) {
	if (kind === "grn" || kind === "rst") {
		return mandi_book_html_table(
			[
				__("GRN No."),
				__("Rst No."),
				__("Vehicle No."),
				__("Load Wt"),
				__("Tare Wt"),
				__("Gross Wt"),
				__("Gunny Type"),
				__("Gunny Wt"),
				__("Deduction"),
				__("Net Wt"),
			],
			lines.map((line) => [
				mandi_book_doc_link("GRN Note", line.grn_name, line.grn_no || line.grn_name),
				line.rst_no
					? (line.weigh_bridge_measurement
						? mandi_book_doc_link("Weigh Bridge Measurement", line.weigh_bridge_measurement, line.rst_no)
						: frappe.utils.escape_html(line.rst_no))
					: (line.weigh_bridge_measurement
						? mandi_book_doc_link("Weigh Bridge Measurement", line.weigh_bridge_measurement)
						: "—"),
				frappe.utils.escape_html(line.vehicle_no || line.actual_vehicle_no || "—"),
				mandi_book_qty(line.load_weight, 3),
				mandi_book_qty(line.tare_weight, 3),
				mandi_book_qty(line.gross_weight, 3),
				frappe.utils.escape_html(line.gunny_type || "—"),
				mandi_book_qty(line.gunny_weight, 3),
				mandi_book_qty(line.deduction, 3),
				mandi_book_qty(line.net_weight, 3),
			]),
			__("No GRN on this TP")
		);
	}
	return mandi_book_html_table(
		[__("Entry"), __("Agent Name"), __("Quantity"), __("Price per Quintal"), __("Total Amount")],
		lines.map((line) => [
			mandi_book_doc_link("Entry", line.entry),
			frappe.utils.escape_html(line.agent_name || "—"),
			mandi_book_qty(line.entry_quantity, 3),
			mandi_book_qty(line.entry_price_per_quintal, 2),
			mandi_book_qty(line.total_amount, 2),
		]),
		__("No Entry on this TP")
	);
}

function mandi_book_html_table(headers, body, empty_text) {
	if (!body.length) {
		return `<div class="text-muted" style="padding:8px 4px;">${frappe.utils.escape_html(empty_text)}</div>`;
	}
	const head = headers.map((label) => `<th>${frappe.utils.escape_html(label)}</th>`).join("");
	const rows = body
		.map((cells) => `<tr>${cells.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
		.join("");
	return `<div style="overflow:auto;"><table class="table table-bordered table-sm" style="margin-bottom:0;"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function mandi_book_doc_link(doctype, name, label) {
	if (!name) {
		return "—";
	}
	const display = label || name;
	const route = frappe.utils.get_form_link(doctype, name);
	return `<a href="${route}">${frappe.utils.escape_html(display)}</a>`;
}

function mandi_book_qty(value, precision) {
	const number = flt(value);
	return frappe.utils.escape_html(number.toFixed(precision));
}
