// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Abstract Report"] = {
	collapsible_filters: true,
	filters: [
		{
			fieldname: "season",
			label: __("Season"),
			fieldtype: "Link",
			options: "Season Master",
		},
		{
			fieldname: "ppc_name",
			label: __("PPC Name"),
			fieldtype: "Link",
			options: "PPC Master",
			get_query: () => {
				const season = frappe.query_report.get_filter_value("season");
				const mill_name = frappe.query_report.get_filter_value("mill_name");
				return {
					query: "ivri_od.procurement.report.abstract_report.abstract_report.get_eligible_ppcs_query",
					filters: {
						season: season || "",
						mill_name: mill_name || "",
					},
				};
			},
		},
		{
			fieldname: "mill_name",
			label: __("Mill"),
			fieldtype: "Link",
			options: "Mill Master",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		const fieldname = (column && (column.fieldname || column.id)) || "";
		if (
			fieldname.endsWith("_target") ||
			fieldname.endsWith("_received") ||
			fieldname.endsWith("_balance") ||
			fieldname === "total_target" ||
			fieldname === "total_received" ||
			fieldname === "total_balance"
		) {
			const num = flt(value);
			return `<div style="text-align: right; font-variant-numeric: tabular-nums;">${num.toFixed(3)}</div>`;
		}
		if (fieldname === "season" || fieldname === "ppc_display" || fieldname === "ppc") {
			if (!data || value === __("Total") || value === "Total") {
				return "";
			}
			if (fieldname === "season") {
				return default_formatter(value, row, column, data);
			}
			const ppc_id = data ? (data.ppc_name || value) : value;
			return `<a class="grey" href="/app/ppc-master/${encodeURIComponent(ppc_id)}" data-doctype="PPC Master" data-name="${encodeURIComponent(ppc_id)}">${frappe.utils.escape_html(value)}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
	after_datatable_render(datatable_obj) {
		inject_abstract_report_styles();
		render_grouped_super_header(datatable_obj);
		if (datatable_obj && datatable_obj.wrapper) {
			$(datatable_obj.wrapper).find(".dt-row-total .dt-cell--col-1, .dt-row-total .dt-cell--col-2, .dt-row--total .dt-cell--col-1, .dt-row--total .dt-cell--col-2").empty();
		}
		if (!datatable_obj.__abstract_header_bound) {
			datatable_obj.__abstract_header_bound = true;
			$(window).off("resize.abstract_report").on("resize.abstract_report", () => {
				render_grouped_super_header(datatable_obj);
			});
		}
		if (!datatable_obj.__abstract_events_bound && datatable_obj.on) {
			datatable_obj.__abstract_events_bound = true;
			datatable_obj.on("onSortColumn", () => render_grouped_super_header(datatable_obj));
			datatable_obj.on("onSwitchColumn", () => render_grouped_super_header(datatable_obj));
			datatable_obj.on("onResizeColumn", () => render_grouped_super_header(datatable_obj));
		}
	},
};

function inject_abstract_report_styles(divider_col_indices = [], season_col_index = null) {
	let style = document.getElementById("abstract-report-matrix-styles");
	if (!style) {
		style = document.createElement("style");
		style.id = "abstract-report-matrix-styles";
		document.head.appendChild(style);
	}

	let divider_css = "";
	if (divider_col_indices && divider_col_indices.length > 0) {
		const selectors = divider_col_indices
			.filter((idx) => idx != null && idx >= 0)
			.map((idx) => `.report-wrapper .dt-cell--col-${idx}, .datatable .dt-cell--col-${idx}`)
			.join(",\n\t\t");
		if (selectors) {
			divider_css = `
		${selectors} {
			border-right: 2px solid #64748b !important;
		}
			`;
		}
	}

	let season_no_border_css = "";
	if (season_col_index != null && season_col_index >= 0) {
		season_no_border_css = `
		.report-wrapper .dt-cell--col-${season_col_index},
		.datatable .dt-cell--col-${season_col_index},
		.dt-super-cell--season {
			border-right: none !important;
		}
		`;
	}

	style.textContent = `
		.dt-row-super-header {
			display: flex;
			background-color: var(--dt-header-cell-bg, #f1f5f9);
			border-bottom: 2px solid var(--gray-600, #4c5a67) !important;
			min-height: 58px;
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
			padding: 6px 8px;
			text-align: center;
			box-sizing: border-box;
			background-color: var(--dt-header-cell-bg, #f8fafc);
			color: var(--text-color, #1e293b);
			display: flex;
			flex-direction: column;
			justify-content: center;
			align-items: center;
			overflow: hidden;
			flex-shrink: 0;
			margin: 0;
		}
		.report-wrapper .dt-row-header,
		.datatable .dt-row-header {
			border-top: none !important;
			margin: 0;
			padding: 0;
		}
		.report-wrapper .dt-row-header .dt-cell--header,
		.datatable .dt-row-header .dt-cell--header {
			border-top: none !important;
		}
		.dt-super-cell:first-child {
			border-left: 1px solid var(--dt-border-color, #cbd5e1);
		}
		.dt-super-cell--spacer {
			background-color: var(--dt-header-cell-bg, #f1f5f9);
			font-weight: 600;
			font-size: 11px;
			color: var(--text-muted, #64748b);
		}
		.dt-super-cell--row-index-divider {
			border-right: 2px solid #64748b !important;
		}
		.dt-super-cell--season {
			border-right: none !important;
		}
		.dt-super-cell--ppc-divider {
			border-right: 2px solid #64748b !important;
		}
		.dt-super-cell--mill {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
			background-color: #dbeafe !important;
			color: #1e3a8a !important;
		}
		.dt-super-cell--mill .dt-super-cell-title {
			color: #1e3a8a !important;
		}
		.dt-super-cell--mill .dt-super-cell-subtitle {
			color: #1e40af !important;
		}
		.dt-super-cell--total {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
			background-color: #dbeafe !important;
			color: #1e3a8a !important;
			font-weight: 800;
		}
		.dt-super-cell--total .dt-super-cell-title {
			color: #1e3a8a !important;
		}
		.dt-super-cell-title {
			font-size: 12px;
			font-weight: 700;
			line-height: 1.3;
			white-space: normal;
			word-wrap: break-word;
			overflow-wrap: break-word;
			text-align: center;
			color: var(--text-color, #0f172a);
			width: 100%;
			max-width: 100%;
		}
		.dt-super-cell-subtitle {
			font-size: 11px;
			font-weight: 600;
			color: var(--text-muted, #475569);
			line-height: 1.2;
			margin-top: 3px;
			white-space: nowrap;
			text-align: center;
			width: 100%;
		}
		.dt-cell--balance-divider {
			border-right: 2px solid #64748b !important;
		}
		${divider_css}
		${season_no_border_css}
	`;
}

function render_grouped_super_header(datatable_obj) {
	if (!datatable_obj || !datatable_obj.header || !datatable_obj.datamanager) return;

	const $headerRow = $(datatable_obj.header).find(".dt-row-header");
	if (!$headerRow.length) return;

	const columns = datatable_obj.datamanager.getColumns();
	if (!columns || !columns.length) return;

	// First determine dividers and apply CSS so DOM measurements include final borders
	const dividerColIndices = [];
	let seasonColIndex = null;
	for (let idx = 0; idx < columns.length; idx++) {
		const c = columns[idx];
		const fn = c.id || c.fieldname || "";
		if (fn === "season") {
			seasonColIndex = c.colIndex != null ? c.colIndex : idx;
		} else if (
			fn === "_rowIndex" ||
			fn === "ppc_display" ||
			fn === "ppc" ||
			(fn.endsWith("_target") && fn !== "total_target") ||
			fn.endsWith("_received") ||
			fn.endsWith("_balance") ||
			fn === "total_target" ||
			fn === "total_received" ||
			fn === "total_balance"
		) {
			const colIdx = c.colIndex != null ? c.colIndex : idx;
			if (!dividerColIndices.includes(colIdx)) {
				dividerColIndices.push(colIdx);
			}
		}
	}
	inject_abstract_report_styles(dividerColIndices, seasonColIndex);

	let $superHeader = $(datatable_obj.header).find(".dt-row-super-header");
	if (!$superHeader.length) {
		$superHeader = $('<div class="dt-row dt-row-super-header"></div>');
		$headerRow.before($superHeader);
	}
	$superHeader.empty();

	const totalRowWidth = $headerRow[0] ? ($headerRow[0].scrollWidth || $headerRow.outerWidth()) : 0;
	if (totalRowWidth > 0) {
		$superHeader.css({
			"width": totalRowWidth + "px",
			"min-width": totalRowWidth + "px"
		});
	}

	const getHeaderCellRect = (colIndex) => {
		if (colIndex == null) return null;
		const cell = $headerRow.find(`.dt-cell--header-${colIndex}`)[0];
		if (cell) {
			const rect = cell.getBoundingClientRect();
			if (rect && rect.width > 0) return rect;
		}
		return null;
	};

	const getColWidth = (col) => {
		if (!col) return 0;
		const rect = getHeaderCellRect(col.colIndex);
		if (rect && rect.width > 0) return rect.width;
		if (col.colIndex != null) {
			const cell = $headerRow.find(`.dt-cell--header-${col.colIndex}`)[0];
			if (cell && cell.offsetWidth) return cell.offsetWidth;
		}
		return parseFloat(col.width) || 140;
	};

	const getGroupWidth = (startCol, endCol, fallbackSum) => {
		const startRect = getHeaderCellRect(startCol ? startCol.colIndex : null);
		const endRect = getHeaderCellRect(endCol ? endCol.colIndex : null);
		if (startRect && endRect && endRect.right >= startRect.left) {
			const w = endRect.right - startRect.left;
			if (w > 0) return w;
		}
		return fallbackSum;
	};

	const toPx = (val) => `${Number(val).toFixed(2)}px`;

	let i = 0;
	while (i < columns.length) {
		const col = columns[i];
		const fieldname = col.id || col.fieldname || "";

		if (fieldname === "_rowIndex") {
			const width = getColWidth(col);
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--spacer dt-super-cell--row-index-divider" style="width: ${toPx(width)}; min-width: ${toPx(width)}; max-width: ${toPx(width)}; flex: 0 0 ${toPx(width)};">
					<div class="dt-super-cell-title">#</div>
				</div>
			`);
			$superHeader.append($cell);
			i++;
		} else if (fieldname === "season" || fieldname === "ppc_display" || fieldname === "ppc") {
			const isSeason = fieldname === "season";
			const label = isSeason ? __("Season") : __("PPC");
			const width = getColWidth(col);
			const dividerClass = isSeason ? "dt-super-cell--season" : "dt-super-cell--ppc-divider";
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--spacer ${dividerClass}" style="width: ${toPx(width)}; min-width: ${toPx(width)}; max-width: ${toPx(width)}; flex: 0 0 ${toPx(width)};">
					<div class="dt-super-cell-title">${frappe.utils.escape_html(label)}</div>
				</div>
			`);
			$superHeader.append($cell);
			i++;
		} else if (fieldname.endsWith("_target") && fieldname !== "total_target") {
			// Mill group: target, received, balance
			const millName = col.mill_name || "";
			const millCode = col.mill_code || "";
			const targetCol = columns[i];
			const receivedCol = columns[i + 1] || {};
			const balanceCol = columns[i + 2] || {};

			const fallbackSum = getColWidth(targetCol) + getColWidth(receivedCol) + getColWidth(balanceCol);
			const totalWidth = getGroupWidth(targetCol, balanceCol, fallbackSum);

			const titleTooltip = millCode ? `${millName} (${millCode})` : millName;
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--mill" title="${frappe.utils.escape_html(titleTooltip)}"
					style="width: ${toPx(totalWidth)}; min-width: ${toPx(totalWidth)}; max-width: ${toPx(totalWidth)}; flex: 0 0 ${toPx(totalWidth)};">
					<div class="dt-super-cell-title">${frappe.utils.escape_html(millName)}</div>
					${millCode ? `<div class="dt-super-cell-subtitle">(${frappe.utils.escape_html(millCode)})</div>` : ""}
				</div>
			`);
			$superHeader.append($cell);

			// Tooltips on individual sub-headers
			set_column_header_tooltip(datatable_obj, targetCol.colIndex, `${titleTooltip} — ${__("Target")}`);
			set_column_header_tooltip(datatable_obj, receivedCol.colIndex, `${titleTooltip} — ${__("Received")}`);
			set_column_header_tooltip(datatable_obj, balanceCol.colIndex, `${titleTooltip} — ${__("Balance")}`);

			i += 3;
		} else if (fieldname === "total_target") {
			// Total group: total_target, total_received, total_balance
			const tTarget = columns[i];
			const tReceived = columns[i + 1] || {};
			const tBalance = columns[i + 2] || {};

			const fallbackSum = getColWidth(tTarget) + getColWidth(tReceived) + getColWidth(tBalance);
			const totalWidth = getGroupWidth(tTarget, tBalance, fallbackSum);

			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--total" title="${__("Total Target, Received & Balance across all Mills")}"
					style="width: ${toPx(totalWidth)}; min-width: ${toPx(totalWidth)}; max-width: ${toPx(totalWidth)}; flex: 0 0 ${toPx(totalWidth)};">
					<div class="dt-super-cell-title">${__("Grand Total")}</div>
				</div>
			`);
			$superHeader.append($cell);

			set_column_header_tooltip(datatable_obj, tTarget.colIndex, `${__("Overall")} — ${__("Total Target")}`);
			set_column_header_tooltip(datatable_obj, tReceived.colIndex, `${__("Overall")} — ${__("Total Received")}`);
			set_column_header_tooltip(datatable_obj, tBalance.colIndex, `${__("Overall")} — ${__("Total Balance")}`);

			i += 3;
		} else {
			const width = getColWidth(col);
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--spacer" style="width: ${toPx(width)}; min-width: ${toPx(width)}; max-width: ${toPx(width)}; flex: 0 0 ${toPx(width)};"></div>
			`);
			$superHeader.append($cell);
			i++;
		}
	}
}

function set_column_header_tooltip(datatable_obj, colIndex, tooltip) {
	if (colIndex == null) return;
	const $cell = $(datatable_obj.header).find(`.dt-cell--header-${colIndex}`);
	if ($cell.length) {
		$cell.attr("title", tooltip);
		$cell.find(".dt-cell__content").attr("title", tooltip);
	}
}

function mark_balance_divider(datatable_obj, colIndex) {
	if (colIndex == null) return;
	$(datatable_obj.wrapper).find(`.dt-cell--col-${colIndex}`).addClass("dt-cell--balance-divider");
}
