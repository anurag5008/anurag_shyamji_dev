// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// ERPNext's "Warehouse Wise Stock Balance" report lists every Company in its Company filter. Here that filter lists only
// the legal Companies (the Companies the operating units account to; see ivri_od/procurement/legal_companies.py).
// The filter is also made wide enough to show the full Company name. The width is responsive (it follows the screen
// and never exceeds the filter bar). ERPNext itself is not changed: when the report script defines its settings, the
// Company filter is given a query and a class, and the width rule below applies to that class only.
(function () {
	const REPORT = "Warehouse Wise Stock Balance";
	const QUERY = "ivri_od.procurement.legal_companies.legal_company_query";
	const LIST = "ivri_od.procurement.legal_companies.get_legal_companies";
	const WIDE_CLASS = "ivri-wide-company-filter";
	const STYLE_ID = "ivri-wide-company-filter-style";

	function add_width_style() {
		if (document.getElementById(STYLE_ID)) {
			return;
		}
		const style = document.createElement("style");
		style.id = STYLE_ID;
		// the filter bar is a wrapping flex row: a basis that grows with the screen, between 360px and 480px,
		// and never wider than the bar itself (so it also fits a phone)
		style.textContent = `
			.page-form .frappe-control.${WIDE_CLASS} {
				flex: 0 0 clamp(360px, 40vw, 480px);
				width: clamp(360px, 40vw, 480px);
				max-width: 100%;
			}
			.page-form .frappe-control.${WIDE_CLASS} input {
				text-overflow: ellipsis;
			}`;
		document.head.appendChild(style);
	}

	function widen_company_filter(report) {
		const control = report && report.get_filter && report.get_filter("company", false);
		if (control && control.$wrapper) {
			control.$wrapper.addClass(WIDE_CLASS);
		}
	}

	function clear_other_company(report) {
		// a Company that is not a legal one (for example a user default) must not stay in the filter
		const control = report && report.get_filter && report.get_filter("company", false);
		const value = control && control.get_value();
		if (!value) {
			return;
		}
		return frappe.xcall(LIST).then((names) => {
			if (!names.includes(value)) {
				control.set_value("");
			}
		});
	}

	function restrict(settings) {
		if (!settings || settings._legal_company_filter) {
			return settings;
		}
		const filter = (settings.filters || []).find((df) => df.fieldname === "company");
		if (!filter) {
			return settings;
		}
		filter.get_query = () => ({ query: QUERY });
		const previous = settings.onload;
		settings.onload = function (report) {
			add_width_style();
			widen_company_filter(report);
			const first = previous ? previous.apply(this, arguments) : undefined;
			return Promise.resolve(first).then(() => clear_other_company(report));
		};
		settings._legal_company_filter = true;
		return settings;
	}

	frappe.provide("frappe.query_reports");
	let stored = frappe.query_reports[REPORT];
	if (stored) {
		stored = restrict(stored);
	}
	// Frappe loads the report script only while this key is empty, so the getter returns nothing until the
	// report's own script assigns its settings; the setter then adds the Company query and keeps them.
	Object.defineProperty(frappe.query_reports, REPORT, {
		configurable: true,
		enumerable: true,
		get() {
			return stored;
		},
		set(settings) {
			stored = restrict(settings);
		},
	});
})();
