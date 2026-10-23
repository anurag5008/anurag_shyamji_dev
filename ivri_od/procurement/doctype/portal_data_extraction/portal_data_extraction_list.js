// Copyright (c) 2026, Profezzo and contributors

const PORTAL_NEW_GROUP = __("Add");

function setup_portal_new_menu(page) {
	page.clear_primary_action();

	const $existing = page.get_inner_group_button(PORTAL_NEW_GROUP);
	if ($existing.length) {
		$existing.remove();
	}

	frappe.db
		.get_list("Portal Site", {
			filters: { enabled: 1 },
			fields: ["name"],
			order_by: "creation asc",
			limit: 50,
		})
		.then((sites) => {
			sites.forEach(({ name }) => {
				page.add_inner_button(
					name,
					() => frappe.new_doc("Portal Data Extraction", { site: name }),
					PORTAL_NEW_GROUP
				);
			});
			// PPAS is its own DocType (PPAS Data Extraction), not a Portal Site.
			if (frappe.model.can_create("PPAS Data Extraction")) {
				page.add_inner_button(__("PPAS"), () => frappe.new_doc("PPAS Data Extraction"), PORTAL_NEW_GROUP);
			}
			page.set_inner_btn_group_as_primary(PORTAL_NEW_GROUP);
		});
}

frappe.listview_settings["Portal Data Extraction"] = {
	add_fields: ["last_extracted_on", "last_section"],

	// Last Extracted On: date and time, tagged "Today" (green) or how long ago (orange),
	// so the list shows at a glance whether each portal was read today.
	formatters: {
		last_extracted_on(value) {
			if (!value) {
				return `<span class="text-muted">${__("Never")}</span>`;
			}
			const shown = frappe.datetime.str_to_user(value);
			const days = frappe.datetime.get_day_diff(frappe.datetime.get_today(), value.slice(0, 10));
			const tag =
				days === 0
					? `<span class="indicator-pill green">${__("Today")}</span>`
					: `<span class="indicator-pill orange">${days === 1 ? __("Yesterday") : __("{0} days ago", [days])}</span>`;
			return `${tag} ${shown}`;
		},
	},

	get_indicator(doc) {
		const colors = { Draft: "gray", Connected: "blue", Completed: "green", Failed: "red" };
		return [__(doc.status), colors[doc.status] || "gray", `status,=,${doc.status}`];
	},

	onload(listview) {
		setup_portal_new_menu(listview.page);

		listview.set_primary_action = function () {
			setup_portal_new_menu(this.page);
		};
	},
};
