// Copyright (c) 2026, Profezzo and contributors

frappe.ui.form.on("Depo Master", {
	setup(frm) {
		frm.set_query("district", () => ({
			filters: { is_active: 1 },
		}));
		frm.set_query("agent", () => ({
			filters: { is_active: 1 },
		}));
	},
});
