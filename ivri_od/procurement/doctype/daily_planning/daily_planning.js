// Copyright (c) 2026, Profezzo and contributors
// For license information, please see license.txt

// TODO: set false to limit plan date to today + 3 days again
const ALLOW_ANY_PLAN_DATE = true;

frappe.ui.form.on("Daily Planning", {
	onload(frm) {
		restrict_plan_date(frm);
	},
	refresh(frm) {
		restrict_plan_date(frm);
		update_trucks_from_transit_pass(frm);
	},
	plan_date(frm) {
		validate_plan_date(frm);
		update_trucks_from_transit_pass(frm);
	},
	ppc_name(frm) {
		update_trucks_from_transit_pass(frm);
	},
	trucks_sent(frm) {
		calculate_estimated_paddy(frm);
		update_trucks_from_transit_pass(frm);
	},
	average_truck_capacity(frm) {
		calculate_estimated_paddy(frm);
	},
	before_save(frm) {
		return sync_trucks_before_save(frm);
	},
});

function get_allowed_date_range() {
	const today = frappe.datetime.get_today();
	return {
		min: today,
		max: frappe.datetime.add_days(today, 3),
	};
}

function restrict_plan_date(frm) {
	if (ALLOW_ANY_PLAN_DATE) {
		frm.fields_dict.plan_date.datepicker?.update({
			minDate: null,
			maxDate: null,
		});
		return;
	}

	const { min, max } = get_allowed_date_range();
	frm.set_df_property("plan_date", "options", "");
	frm.fields_dict.plan_date.datepicker?.update({
		minDate: frappe.datetime.str_to_obj(min),
		maxDate: frappe.datetime.str_to_obj(max),
	});
}

function validate_plan_date(frm) {
	if (ALLOW_ANY_PLAN_DATE || !frm.doc.plan_date) return;

	const { min, max } = get_allowed_date_range();
	if (frm.doc.plan_date < min || frm.doc.plan_date > max) {
		frappe.msgprint(
			__("Daily Planning is allowed only for today and the next 3 days ({0} to {1})", [
				frappe.datetime.str_to_user(min),
				frappe.datetime.str_to_user(max),
			])
		);
		frm.set_value("plan_date", min);
	}
}

function sync_trucks_before_save(frm) {
	return new Promise((resolve) => {
		if (!frm.doc.plan_date || !frm.doc.ppc_name) {
			frm.set_value("trucks_loaded", 0);
			frm.set_value(
				"trucks_remaining",
				Math.max(cint(frm.doc.trucks_sent), 0)
			);
			resolve();
			return;
		}

		frappe.call({
			method:
				"ivri_od.procurement.doctype.daily_planning.daily_planning.get_truck_load_from_transit_pass",
			args: {
				plan_date: frm.doc.plan_date,
				ppc_name: frm.doc.ppc_name,
				trucks_sent: frm.doc.trucks_sent,
			},
			callback(r) {
				if (r.message) {
					frm.set_value("trucks_loaded", r.message.trucks_loaded || 0);
					frm.set_value("trucks_remaining", r.message.trucks_remaining || 0);
				}
				resolve();
			},
			error() {
				resolve();
			},
		});
	});
}

function update_trucks_from_transit_pass(frm) {
	if (!frm.doc.plan_date || !frm.doc.ppc_name) {
		frm.set_value("trucks_loaded", 0);
		frm.set_value(
			"trucks_remaining",
			Math.max(cint(frm.doc.trucks_sent) - 0, 0)
		);
		return;
	}

	frappe.call({
		method:
			"ivri_od.procurement.doctype.daily_planning.daily_planning.get_truck_load_from_transit_pass",
		args: {
			plan_date: frm.doc.plan_date,
			ppc_name: frm.doc.ppc_name,
			trucks_sent: frm.doc.trucks_sent,
		},
		callback(r) {
			if (!r.message) return;
			frm.set_value("trucks_loaded", r.message.trucks_loaded || 0);
			frm.set_value("trucks_remaining", r.message.trucks_remaining || 0);
		},
	});
}

function calculate_estimated_paddy(frm) {
	const trucks = flt(frm.doc.trucks_sent);
	const capacity = flt(frm.doc.average_truck_capacity) || 250;
	frm.set_value("estimated_paddy", trucks * capacity);
}
