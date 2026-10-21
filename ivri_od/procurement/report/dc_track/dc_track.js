// Copyright (c) 2026, Profezzo and contributors

// One line per DC: lots to deliver (View DC from DCRO) against lots delivered
// (DC Transit Challan from DCRO for FCI, Lot Search from SCMS for RRC), joined on the DC No.
// Report scripts run inside new Function(): functions called from a cell's onclick
// must be global, so they live on ivri_od.dc_track.
frappe.provide("ivri_od.dc_track");

const DC_TRACK_COLOURS = {
	Fulfilled: "green",
	"Partly Delivered": "orange",
	"Not Started": "red",
	"Over Delivered": "purple",
	"Lots Not Read": "grey",
	"No Lots on DC": "grey",
	"DC Not in View DC": "grey",
};

frappe.query_reports["DC Track"] = {
	collapsible_filters: true,
	filters: [
		{ fieldname: "mill_id", label: __("Mill No."), fieldtype: "Link", options: "Mill Master" },
		{ fieldname: "dc_no", label: __("DC No."), fieldtype: "Data" },
		{ fieldname: "from_date", label: __("DC Date From"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("DC Date To"), fieldtype: "Date" },
		{ fieldname: "dc_type", label: __("DC Type"), fieldtype: "Select", options: "\nFCI\nRRC" },
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", ...Object.keys(DC_TRACK_COLOURS)].join("\n"),
		},
	],
	// Charts above the table, drawn from the report rows: they follow every filter change.
	after_refresh(report) {
		ivri_od.dc_track.render_charts(report);
	},
	formatter(value, row, column, data, default_formatter) {
		if (column.fieldname === "dc_note" && data) {
			return ivri_od.dc_track.file_link(data.dc_note);
		}
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		// Lots Delivered: pop-up of the delivered lots with their acknowledgement files.
		if (column.fieldname === "delivered_lots" && (data.delivered_lots || data.not_counted)) {
			const dc_no = frappe.utils.escape_html(data.dc_no);
			return `<a href="#" onclick="ivri_od.dc_track.show_lots('${dc_no}'); return false;">${value}</a>`;
		}
		if (column.fieldname === "status" && DC_TRACK_COLOURS[data.status]) {
			return `<span class="indicator-pill ${DC_TRACK_COLOURS[data.status]}">${value}</span>`;
		}
		if (column.fieldname === "remaining_lots" && data.remaining_lots > 0) {
			return `<b class="text-danger">${value}</b>`;
		}
		return value;
	},
};

// Saved file as a "Download" link, else "Not saved".
ivri_od.dc_track.file_link = function (url, label = __("Download")) {
	return url
		? `<a href="${encodeURI(url)}" target="_blank" rel="noopener">${frappe.utils.escape_html(label)}</a>`
		: `<span class="text-muted">${__("Not saved")}</span>`;
};

// Delivered lots of one DC as a table (as read from the portal), with links to the files saved
// from each row: FCI - Details and Acknowledgement Note (DCRO DC Transit Challan);
// RRC - Acknowledgement (SCMS Lot Search). See get_delivered_lots in dc_track.py.
ivri_od.dc_track.show_lots = function (dc_no) {
	frappe.xcall("ivri_od.procurement.report.dc_track.dc_track.get_delivered_lots", { dc_no }).then((r) => {
		const esc = frappe.utils.escape_html;
		const headers = [];
		r.lots.forEach((lot) => Object.keys(lot.cells).forEach((h) => !headers.includes(h) && headers.push(h)));
		const file_labels = [...(r.file_labels || [])];
		r.lots.forEach((lot) => lot.files.forEach((f) => !file_labels.includes(f.label) && file_labels.push(f.label)));
		const colours = { Counted: "green", "Read Twice": "grey" };
		const body = r.lots
			.map((lot) => {
				const files = file_labels.map((label) => {
					const file = lot.files.find((f) => f.label === label);
					return `<td>${ivri_od.dc_track.file_link(file && file.url)}</td>`;
				});
				return `<tr>
					<td><span class="indicator-pill ${colours[lot.counted] || "red"}">${esc(lot.counted)}</span></td>
					<td>${esc(lot.source)}</td>
					${headers.map((h) => `<td>${esc(lot.cells[h] || "")}</td>`).join("")}
					${files.join("")}
				</tr>`;
			})
			.join("");
		const html = `
			<p>${__("DC Type")}: <b>${esc(r.dc_type || "")}</b> &nbsp; ${__("Lots Delivered")}: <b>${r.counted}</b>
				&nbsp; ${__("DC Note")}: ${ivri_od.dc_track.file_link(r.dc_note)}</p>
			<div style="overflow-x: auto">
				<table class="table table-bordered table-sm">
					<thead><tr>
						<th>${__("Counted")}</th><th>${__("Delivered From")}</th>
						${headers.map((h) => `<th>${esc(h)}</th>`).join("")}
						${file_labels.map((l) => `<th>${esc(l)}</th>`).join("")}
					</tr></thead>
					<tbody>${body || `<tr><td colspan="2" class="text-muted">${__("No lots read")}</td></tr>`}</tbody>
				</table>
			</div>`;
		const dialog = new frappe.ui.Dialog({
			title: __("Delivered Lots of DC {0}", [r.dc_no]),
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "lots" }],
		});
		dialog.fields_dict.lots.$wrapper.html(html);
		dialog.show();
	});
};

// ---------------------------------------------------------------
// Charts: DCs by Status (donut) and lots per DC (stacked bar)
// ---------------------------------------------------------------

// Status is a state: fixed status colours (green / amber / coral / red), grey for "nothing to show".
const DC_TRACK_STATUS_COLOURS = {
	Fulfilled: "#0ca30c",
	"Partly Delivered": "#fab219",
	"Over Delivered": "#ec835a",
	"Not Started": "#d03b3b",
	"Lots Not Read": "#8a8984",
	"No Lots on DC": "#b5b4ae",
	"DC Not in View DC": "#6b6a65",
};
// Bar series (checked for colour-blind separation): Delivered blue, Remaining orange; own steps in dark mode.
const DC_TRACK_BAR_COLOURS = { light: ["#2a78d6", "#eb6834"], dark: ["#3987e5", "#d95926"] };
// More DCs than this: the bar chart shows the latest ones (the table still lists all).
const DC_TRACK_MAX_BARS = 30;

ivri_od.dc_track.render_charts = function (report) {
	report.page.main.find(".dc-track-charts").remove();
	const rows = report.data || [];
	if (!rows.length || typeof frappe.Chart === "undefined") {
		return;
	}
	const $panel = $(`
		<div class="dc-track-charts" style="display: flex; flex-wrap: wrap; gap: 16px; margin: 0 0 16px;">
			<div class="frappe-card" style="flex: 1 1 300px; min-width: 0; padding: 12px;">
				<div class="text-muted small">${__("DCs by Status")}</div>
				<div class="dc-track-status"></div>
			</div>
			<div class="frappe-card" style="flex: 2 1 480px; min-width: 0; padding: 12px;">
				<div class="text-muted small dc-track-bar-title"></div>
				<div class="dc-track-lots"></div>
			</div>
		</div>`);
	$panel.insertBefore(report.$report);

	// Donut: one slice per status present, in a fixed order (a filter never repaints a status).
	const counts = {};
	rows.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
	const statuses = Object.keys(DC_TRACK_STATUS_COLOURS).filter((s) => counts[s]);
	new frappe.Chart($panel.find(".dc-track-status")[0], {
		type: "donut",
		height: 260,
		data: { labels: statuses.map((s) => __(s)), datasets: [{ values: statuses.map((s) => counts[s]) }] },
		colors: statuses.map((s) => DC_TRACK_STATUS_COLOURS[s]),
		maxSlices: statuses.length,
	});

	// Stacked bar: lots delivered and still to deliver, per DC in DC date order.
	let dcs = rows.filter((r) => r.total_lots !== null && r.total_lots !== undefined && r.total_lots > 0);
	dcs.sort((a, b) => (a.dc_date || "").localeCompare(b.dc_date || "") || a.dc_no.localeCompare(b.dc_no));
	const capped = dcs.length > DC_TRACK_MAX_BARS;
	dcs = dcs.slice(-DC_TRACK_MAX_BARS);
	$panel
		.find(".dc-track-bar-title")
		.text(
			capped
				? __("Lots per DC: latest {0} DCs (filter to see others)", [DC_TRACK_MAX_BARS])
				: __("Lots per DC")
		);
	if (!dcs.length) {
		$panel.find(".dc-track-lots").html(`<p class="text-muted">${__("No DC with lots to show")}</p>`);
		return;
	}
	const dark = document.documentElement.getAttribute("data-theme") === "dark";
	new frappe.Chart($panel.find(".dc-track-lots")[0], {
		type: "bar",
		height: 260,
		data: {
			labels: dcs.map((r) => r.dc_no),
			datasets: [
				{ name: __("Lots Delivered"), values: dcs.map((r) => Math.min(r.delivered_lots || 0, r.total_lots)) },
				{ name: __("Remaining Lots"), values: dcs.map((r) => Math.max(r.remaining_lots || 0, 0)) },
			],
		},
		colors: DC_TRACK_BAR_COLOURS[dark ? "dark" : "light"],
		barOptions: { stacked: 1, spaceRatio: 0.4 },
		axisOptions: { xAxisMode: "tick", xIsSeries: 1 },
		tooltipOptions: { formatTooltipY: (v) => __("{0} lots", [v]) },
	});
};
