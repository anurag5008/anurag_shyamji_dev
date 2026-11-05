// Copyright (c) 2026, Profezzo and contributors

frappe.ui.form.on("Entry", {
	setup(frm) {
		// Agent Name drop-down: active agents from Agent Master.
		frm.set_query("agent_name", () => ({ filters: { is_active: 1 } }));
	},
	refresh(frm) {
		load_tp_no_choices(frm);
	},
	season(frm) {
		load_tp_no_choices(frm, true);
		try_resolve_pass_from_ppc_tp(frm);
	},
	ppc_name(frm) {
		load_tp_no_choices(frm, true);
		try_resolve_pass_from_ppc_tp(frm);
	},
	tp_no(frm) {
		try_resolve_pass_from_ppc_tp(frm);
	},
	entry_quantity(frm) {
		update_total_amount(frm);
	},
	entry_price_per_quintal(frm) {
		update_total_amount(frm);
	},
});

// TP No drop-down: every Transit Pass No in PPAS Transit Pass for the chosen Season and PPC.
// When Season or PPC changes (clear_old), a TP No that is not in the new list is cleared.
function load_tp_no_choices(frm, clear_old) {
	const season = (frm.doc.season || "").trim();
	const ppc = (frm.doc.ppc_name || "").trim();
	const request_id = (frm.__tp_choices_request_id || 0) + 1;
	frm.__tp_choices_request_id = request_id;

	const apply = (numbers) => {
		const field = frm.fields_dict.tp_no;
		if (field) {
			// The saved TP No may already be used by this Entry: never reject it for not being in the list.
			field.df.ignore_validation = 1;
			field.df.options = numbers;
			field.set_data(numbers);
		}
		if (clear_old && frm.doc.tp_no && !numbers.includes((frm.doc.tp_no || "").trim())) {
			frm.set_value("tp_no", "");
			frm.set_value("pass_unique_key", "");
			frm.set_value("transit_pass_no", "");
			frm.set_value("tp_quantity", 0);
			frm.set_value("pacs_name", "");
		}
	};

	if (!season || !ppc) {
		apply([]);
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.entry.entry.get_transit_pass_numbers",
		args: { season, ppc_name: ppc, current: frm.is_new() ? "" : frm.doc.name },
		callback(r) {
			if (request_id !== frm.__tp_choices_request_id) return;
			apply(r.message || []);
		},
	});
}

function try_resolve_pass_from_ppc_tp(frm) {
	const season = (frm.doc.season || "").trim();
	const ppc = (frm.doc.ppc_name || "").trim();
	const tp_no = (frm.doc.tp_no || "").trim();
	if (!season || !ppc || !tp_no) {
		return;
	}
	frappe.call({
		method: "ivri_od.procurement.doctype.entry.entry.resolve_entry_pass_from_ppc_tp",
		args: { season, ppc_name: ppc, tp_no },
		freeze: true,
		freeze_message: __("Fetching Pass Unique Key…"),
		callback(r) {
			const data = r.message || {};
			if (!data.pass_unique_key) {
				frappe.msgprint({
					title: __("Transit pass not found"),
					message: __(
						"No PPAS Transit Pass for this Season, PPC, and TP No."
					),
					indicator: "red",
				});
				frm.set_value("pass_unique_key", "");
				return;
			}
			frm.set_value("pass_unique_key", data.pass_unique_key);
			if (data.transit_pass_no) {
				frm.set_value("transit_pass_no", data.transit_pass_no);
			}
			frm.set_value("tp_quantity", data.quantity || 0);
			frm.set_value("pacs_name", data.pacs || "");
			frappe.show_alert({
				message: __("Pass Unique Key loaded from PPAS Transit Pass"),
				indicator: "green",
			});
		},
	});
}

function update_total_amount(frm) {
	const total =
		flt(frm.doc.entry_quantity) *
		flt(frm.doc.entry_price_per_quintal);
	frm.set_value("total_amount", total);
}
