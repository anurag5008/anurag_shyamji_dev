// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// List view settings must live in this *_list.js file: Frappe loads the form script only after a form
// of this DocType has been opened, so settings kept there are missing after a page refresh.

// Miller and PPC names are long ("SHREE SHYAMJI PADDY PROCESSING PVT LTD(M051007)"). The list normally
// cuts them with "...". Here those two columns are wider and wrap onto a second line, so the whole
// name is visible at a glance. Display only: nothing is saved.
const PPAS_LIST_STYLE_ID = "ivri-od-ppas-tp-list-style";

function add_ppas_list_style() {
	if (document.getElementById(PPAS_LIST_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = PPAS_LIST_STYLE_ID;
	style.textContent = `
		.ppas-tp-list .list-row-head .list-subject,
		.ppas-tp-list .list-row .list-subject { flex: 0 0 320px !important; min-width: 320px; }
		.ppas-tp-list .list-row-col[data-fieldname="ppc"] { flex: 0 0 230px !important; width: 230px !important; min-width: 230px; }
		.ppas-tp-list .list-row .list-subject .level-item,
		.ppas-tp-list .list-row .list-subject .ellipsis,
		.ppas-tp-list .list-row .list-subject a,
		.ppas-tp-list .list-row .list-row-col[data-fieldname="ppc"],
		.ppas-tp-list .list-row .list-row-col[data-fieldname="ppc"] .ellipsis,
		.ppas-tp-list .list-row .list-row-col[data-fieldname="ppc"] a {
			white-space: normal !important;
			overflow: visible !important;
			text-overflow: clip !important;
			overflow-wrap: anywhere;
			line-height: 1.35;
		}
		.ppas-tp-list .list-row { height: auto; min-height: var(--list-row-height, 40px); padding-top: 6px; padding-bottom: 6px; }
	`;
	document.head.appendChild(style);
}

frappe.listview_settings["PPAS Transit Pass"] = {
	onload(listview) {
		// Open with no filter: Frappe remembers the filters used last time, which hid data from staff.
		// A link with filters in its address (route options) is left alone.
		if (!Object.keys(frappe.route_options || {}).length && listview.filter_area) {
			listview.filter_area.clear();
		}
		add_ppas_list_style();
		listview.page.wrapper.addClass("ppas-tp-list");
	},
};
