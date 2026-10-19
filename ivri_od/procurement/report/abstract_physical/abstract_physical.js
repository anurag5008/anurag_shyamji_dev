// Copyright (c) 2026, Profezzo and contributors

frappe.query_reports["Abstract Physical"] = {
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
			label: __("PPC"),
			fieldtype: "Link",
			options: "PPC Master",
			get_query: () => {
				const season = frappe.query_report.get_filter_value("season");
				return {
					query: "ivri_od.procurement.report.abstract_report.abstract_report.get_eligible_ppcs_query",
					filters: {
						season: season || "",
					},
				};
			},
		},
	],
	get_datatable_options(options) {
		return Object.assign(options, {
			layout: "fixed",
			cellHeight: 36,
		});
	},
	formatter(value, row, column, data, default_formatter) {
		const fieldname = (column && (column.fieldname || column.id)) || "";
		if (
			[
				"tp_quantity",
				"physical_paddy",
				"entry_qty",
				"chhatni_quantity",
			].includes(fieldname)
		) {
			const num = flt(value);
			return `<div style="text-align: right; font-variant-numeric: tabular-nums;">${num.toFixed(3)}</div>`;
		}
		if (fieldname === "chhatni_pct") {
			const num = flt(value);
			return `<div style="text-align: right; font-variant-numeric: tabular-nums;">${num.toFixed(2)}%</div>`;
		}
		if (fieldname === "ppc" || fieldname === "ppc_name" || fieldname === "ppc_display") {
			const ppc_id = data ? (data.ppc_name || value) : value;
			return `<a class="grey" href="/app/ppc-master/${encodeURIComponent(ppc_id)}" data-doctype="PPC Master" data-name="${encodeURIComponent(ppc_id)}">${frappe.utils.escape_html(value)}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
	after_datatable_render(datatable_obj) {
		render_abstract_physical_super_header(datatable_obj);
	},
};

function render_abstract_physical_super_header(datatable_obj) {
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
		let rowIndexColIndex = -1;
		let lastColIndex = -1;
		const summaryColIndices = [];

		columns.forEach((c) => {
			const fn = c.id || c.fieldname || "";
			const idx = c.colIndex != null ? c.colIndex : -1;
			if (idx < 0) return;
			if (fn === "_rowIndex") {
				rowIndexColIndex = idx;
			} else if (!c.hidden) {
				summaryColIndices.push(idx);
				if (idx > lastColIndex) {
					lastColIndex = idx;
				}
			}
		});

		inject_abstract_physical_styles({
			rowIndexColIndex,
			lastColIndex,
			summaryColIndices,
		});

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
				"max-width": totalRowWidth + "px",
			});
		}

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
			} else {
				let startCol = null;
				let endCol = null;
				let fallbackSum = 0;

				while (i < columns.length) {
					const c = columns[i];
					const fn = c.id || c.fieldname || "";
					if (fn === "_rowIndex") break;
					if (!c.hidden) {
						if (!startCol) startCol = c;
						endCol = c;
						fallbackSum += (parseFloat(c.width) || 120) + 1;
					}
					i++;
				}

				if (startCol && endCol) {
					const totalWidth = getGroupWidth(startCol, endCol, fallbackSum);
					const $cell = $(`
						<div class="dt-super-cell dt-super-cell--summary" title="${__("Summary")}"
							style="width: ${toPx(totalWidth)}; min-width: ${toPx(totalWidth)}; max-width: ${toPx(totalWidth)}; flex: 0 0 ${toPx(totalWidth)};">
							<div class="dt-super-cell-title">${__("Summary")}</div>
						</div>
					`);
					$superHeader.append($cell);
				}
			}
		}
	} finally {
		datatable_obj._super_header_rendering = false;
	}

	if (!datatable_obj.__abstract_phys_bound) {
		datatable_obj.__abstract_phys_bound = true;
		$(window).off("resize.abstract_physical").on("resize.abstract_physical", () => {
			render_abstract_physical_super_header(datatable_obj);
		});
	}
	if (!datatable_obj.__abstract_phys_ro && typeof ResizeObserver !== "undefined" && $headerRow[0]) {
		const ro = new ResizeObserver(() => {
			render_abstract_physical_super_header(datatable_obj);
		});
		ro.observe($headerRow[0]);
		datatable_obj.__abstract_phys_ro = ro;
	}
	if (!datatable_obj.__abstract_phys_events && datatable_obj.on) {
		datatable_obj.__abstract_phys_events = true;
		datatable_obj.on("onSortColumn", () => render_abstract_physical_super_header(datatable_obj));
		datatable_obj.on("onSwitchColumn", () => render_abstract_physical_super_header(datatable_obj));
	}
}

function inject_abstract_physical_styles(col_indices = {}) {
	let style = document.getElementById("abstract-physical-ui-styles");
	if (!style) {
		style = document.createElement("style");
		style.id = "abstract-physical-ui-styles";
		document.head.appendChild(style);
	}

	let vertical_border_css = "";
	const rowIndexCol = col_indices.rowIndexColIndex != null ? col_indices.rowIndexColIndex : -1;
	const lastCol = col_indices.lastColIndex != null ? col_indices.lastColIndex : -1;

	if (rowIndexCol >= 0) {
		vertical_border_css += `
		.report-wrapper .dt-cell--col-${rowIndexCol},
		.datatable .dt-cell--col-${rowIndexCol} {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		`;
	}
	if (lastCol >= 0) {
		vertical_border_css += `
		.report-wrapper .dt-cell--col-${lastCol},
		.datatable .dt-cell--col-${lastCol} {
			border-right: 2px solid var(--gray-600, #4c5a67) !important;
		}
		`;
	}

	let section_header_colors_css = "";
	const summaryCols = col_indices.summaryColIndices || [];
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
		.report-wrapper .dt-scrollable {
			overflow-x: auto !important;
		}
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
		.report-wrapper .dt-cell__content {
			white-space: nowrap;
			text-overflow: ellipsis;
		}
		${vertical_border_css}
		${section_header_colors_css}
	`;
}
