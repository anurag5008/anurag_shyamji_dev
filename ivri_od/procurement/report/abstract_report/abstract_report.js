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
		if (fieldname === "ppc_display" || fieldname === "ppc") {
			const ppc_id = data ? (data.ppc_name || value) : value;
			return `<a class="grey" href="/app/ppc-master/${encodeURIComponent(ppc_id)}" data-doctype="PPC Master" data-name="${encodeURIComponent(ppc_id)}">${frappe.utils.escape_html(value)}</a>`;
		}
		return default_formatter(value, row, column, data);
	},
	after_datatable_render(datatable_obj) {
		inject_abstract_report_styles();
		render_grouped_super_header(datatable_obj);
		if (!datatable_obj.__abstract_header_bound) {
			datatable_obj.__abstract_header_bound = true;
			$(window).off("resize.abstract_report").on("resize.abstract_report", () => {
				render_grouped_super_header(datatable_obj);
			});
		}
	},
};

function inject_abstract_report_styles() {
	let style = document.getElementById("abstract-report-matrix-styles");
	if (!style) {
		style = document.createElement("style");
		style.id = "abstract-report-matrix-styles";
		document.head.appendChild(style);
	}
	style.textContent = `
		.dt-row-super-header {
			display: flex;
			background-color: var(--dt-header-cell-bg, #f1f5f9);
			border-bottom: 2px solid var(--border-color, #cbd5e1);
			min-height: 58px;
		}
		.dt-super-cell {
			border: 1px solid var(--dt-border-color, #cbd5e1);
			border-bottom: none;
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
		.dt-super-cell--mill {
			border-right: 2px solid #64748b !important;
			background-color: #f8fafc;
		}
		.dt-super-cell--total {
			border-right: 2px solid #64748b !important;
			background-color: #f1f5f9;
			font-weight: 800;
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
	`;
}

function render_grouped_super_header(datatable_obj) {
	if (!datatable_obj || !datatable_obj.header || !datatable_obj.datamanager) return;

	const $headerRow = $(datatable_obj.header).find(".dt-row-header");
	if (!$headerRow.length) return;

	const columns = datatable_obj.datamanager.getColumns();
	if (!columns || !columns.length) return;

	let $superHeader = $(datatable_obj.header).find(".dt-row-super-header");
	if (!$superHeader.length) {
		$superHeader = $('<div class="dt-row dt-row-super-header"></div>');
		$headerRow.before($superHeader);
	}
	$superHeader.empty();

	const getColWidth = (col) => {
		if (!col) return 0;
		if (col.colIndex != null) {
			const cell = $headerRow.find(`.dt-cell--header-${col.colIndex}`)[0];
			if (cell && cell.offsetWidth) return cell.offsetWidth;
		}
		return parseInt(col.width, 10) || 140;
	};

	let i = 0;
	while (i < columns.length) {
		const col = columns[i];
		const fieldname = col.id || col.fieldname || "";

		if (fieldname === "_rowIndex") {
			const width = getColWidth(col);
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--spacer" style="width: ${width}px; min-width: ${width}px; max-width: ${width}px; flex: 0 0 ${width}px;"></div>
			`);
			$superHeader.append($cell);
			i++;
		} else if (fieldname === "season" || fieldname === "ppc_display" || fieldname === "ppc") {
			const label = fieldname === "season" ? __("Season") : __("PPC");
			const width = getColWidth(col);
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--spacer" style="width: ${width}px; min-width: ${width}px; max-width: ${width}px; flex: 0 0 ${width}px;">
					<div class="dt-super-cell-title">${frappe.utils.escape_html(label)}</div>
				</div>
			`);
			$superHeader.append($cell);
			i++;
		} else if (fieldname.endsWith("_target")) {
			// Mill group: target, received, balance
			const millName = col.mill_name || "";
			const millCode = col.mill_code || "";
			const targetCol = columns[i];
			const receivedCol = columns[i + 1] || {};
			const balanceCol = columns[i + 2] || {};

			const wTarget = getColWidth(targetCol);
			const wReceived = getColWidth(receivedCol);
			const wBalance = getColWidth(balanceCol);
			const totalWidth = wTarget + wReceived + wBalance;

			const titleTooltip = millCode ? `${millName} (${millCode})` : millName;
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--mill" title="${frappe.utils.escape_html(titleTooltip)}"
					style="width: ${totalWidth}px; min-width: ${totalWidth}px; max-width: ${totalWidth}px; flex: 0 0 ${totalWidth}px;">
					<div class="dt-super-cell-title">${frappe.utils.escape_html(millName)}</div>
					${millCode ? `<div class="dt-super-cell-subtitle">(${frappe.utils.escape_html(millCode)})</div>` : ""}
				</div>
			`);
			$superHeader.append($cell);

			// Tooltips on individual sub-headers
			set_column_header_tooltip(datatable_obj, targetCol.colIndex, `${titleTooltip} — ${__("Target")}`);
			set_column_header_tooltip(datatable_obj, receivedCol.colIndex, `${titleTooltip} — ${__("Received")}`);
			set_column_header_tooltip(datatable_obj, balanceCol.colIndex, `${titleTooltip} — ${__("Balance")}`);

			// Visual border on Balance column
			mark_balance_divider(datatable_obj, balanceCol.colIndex);

			i += 3;
		} else if (fieldname === "total_target") {
			// Total group: total_target, total_received, total_balance
			const tTarget = columns[i];
			const tReceived = columns[i + 1] || {};
			const tBalance = columns[i + 2] || {};

			const wTarget = getColWidth(tTarget);
			const wReceived = getColWidth(tReceived);
			const wBalance = getColWidth(tBalance);
			const totalWidth = wTarget + wReceived + wBalance;

			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--total" title="${__("Total Target, Received & Balance across all Mills")}"
					style="width: ${totalWidth}px; min-width: ${totalWidth}px; max-width: ${totalWidth}px; flex: 0 0 ${totalWidth}px;">
					<div class="dt-super-cell-title">${__("TOTAL")}</div>
				</div>
			`);
			$superHeader.append($cell);

			set_column_header_tooltip(datatable_obj, tTarget.colIndex, `${__("Overall")} — ${__("Total Target")}`);
			set_column_header_tooltip(datatable_obj, tReceived.colIndex, `${__("Overall")} — ${__("Total Received")}`);
			set_column_header_tooltip(datatable_obj, tBalance.colIndex, `${__("Overall")} — ${__("Total Balance")}`);

			mark_balance_divider(datatable_obj, tBalance.colIndex);

			i += 3;
		} else {
			const width = getColWidth(col);
			const $cell = $(`
				<div class="dt-super-cell dt-super-cell--spacer" style="width: ${width}px; min-width: ${width}px; max-width: ${width}px; flex: 0 0 ${width}px;"></div>
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
