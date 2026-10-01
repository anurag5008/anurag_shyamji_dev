"""Ensure Gate Entry / Gate Exit pass buttons via Client Script (survives asset cache issues)."""

import frappe

# Loaded from app file so Client Script stays in sync with public/js/gate_pass.js
SCRIPT_PATH_PARTS = ("public", "js", "gate_pass.js")

GATE_ENTRY_FORM_SCRIPT = """
frappe.ui.form.on("Gate Entry", {
	refresh(frm) {
		ivri_od_schedule_gate_pass_buttons(frm, () => frm.doc.name);
	},
});
"""

GATE_EXIT_FORM_SCRIPT = """
frappe.ui.form.on("Gate Exit", {
	refresh(frm) {
		ivri_od_schedule_gate_pass_buttons(frm, () => frm.doc.gate_entry_in);
	},
});
"""


def _upsert_client_script(name: str, dt: str, script: str):
	helpers = _read_gate_pass_helpers()
	full_script = helpers + "\n" + script
	if frappe.db.exists("Client Script", name):
		doc = frappe.get_doc("Client Script", name)
		doc.script = full_script
		doc.enabled = 1
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(
			{
				"doctype": "Client Script",
				"name": name,
				"dt": dt,
				"view": "Form",
				"enabled": 1,
				"module": "Procurement",
				"script": full_script,
			}
		).insert(ignore_permissions=True)


def _read_gate_pass_helpers() -> str:
	path = frappe.get_app_path("ivri_od", *SCRIPT_PATH_PARTS)
	with open(path, encoding="utf-8") as f:
		return f.read()


def execute():
	_upsert_client_script("Gate Entry Pass Toolbar", "Gate Entry", GATE_ENTRY_FORM_SCRIPT)
	_upsert_client_script("Gate Exit Pass Toolbar", "Gate Exit", GATE_EXIT_FORM_SCRIPT)
	frappe.reload_doc("procurement", "doctype", "gate_entry")
	frappe.reload_doc("procurement", "doctype", "gate_exit")
	frappe.clear_cache(doctype="Gate Entry")
	frappe.clear_cache(doctype="Gate Exit")
