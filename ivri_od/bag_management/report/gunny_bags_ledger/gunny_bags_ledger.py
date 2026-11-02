# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Gunny Bags Ledger: read-only. Rules are in ivri_od/bag_management/gunny_bags_ledger.py.
Reads Weigh Bridge Measurement, Quality Check, GRN Note, PPAS Transit Pass and Gunny Bags Sent to PPC; changes nothing.
Credit Bags come from each trip's own Quality Check (Paddy Received (Bags)); Debit Bags are the Number of Bags Sent
of the submitted Gunny Bags Sent to PPC records of the same Mill + PPC; Remaining Bags = Debit Bags - Credit Bags.
The report is for one Mill Master, chosen in the required Mill Name filter; nothing is shown (and nothing is combined)
until one is selected."""

import frappe
from frappe import _

from ivri_od.bag_management.gunny_bags_ledger import build_ledger_rows, wbms_of_mill
from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name, resolve_ppc_master_name


def execute(filters=None):
	filters = frappe._dict(filters or {})
	mill = (filters.get("mill") or "").strip()
	if not mill:
		return get_columns(), [], _("Select a Mill Name to see the ledger.")
	if not frappe.db.exists("Mill Master", mill):
		frappe.throw(_("Mill {0} was not found in Mill Master.").format(frappe.bold(mill)))
	return get_columns(), get_data(mill)


def get_columns():
	return [
		{"label": _("Mill Name"), "fieldname": "mill_name", "fieldtype": "Data", "width": 420},
		{"label": _("PPC Name"), "fieldname": "ppc_name", "fieldtype": "Data", "width": 220},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "precision": 3, "width": 110},
		{"label": _("Debit Bags"), "fieldname": "debit_bags", "fieldtype": "Int", "width": 120},
		{"label": _("Credit Bags"), "fieldname": "credit_bags", "fieldtype": "Int", "width": 120},
		{"label": _("Remaining Bags"), "fieldname": "remaining_bags", "fieldtype": "Int", "width": 130},
	]


def mill_full_name(mill):
	"""The full name of a Mill Master as it is written there, e.g. "Shree Shyamji Paddy Processing Pvt Ltd (Boiled)"."""
	row = frappe.db.get_value("Mill Master", mill, ["display_name", "company"], as_dict=True) or {}
	return (row.get("display_name") or "").strip() or (row.get("company") or "").strip() or mill


def _names_for(unit, ppc):
	"""Mill and PPC names for a row that exists only through a sent record; the PPC is written like the Transit Pass text."""
	mill = mill_full_name(unit)
	ppc_row = frappe.db.get_value("PPC Master", ppc, ["ppc_name", "code"], as_dict=True)
	return mill, (f"{ppc_row.ppc_name}({ppc_row.code})" if ppc_row else ppc)


def get_data(mill):
	wbms = frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"pass_unique_key": ["is", "set"], "docstatus": ["<", 2]},
		fields=["name", "pass_unique_key", "quality_check", "net_weight"],
	)
	keys = sorted({w.pass_unique_key.strip() for w in wbms})
	tps = {}
	if keys:
		for tp in frappe.get_all(
			"PPAS Transit Pass", filters={"pass_unique_key": ["in", keys]}, fields=["pass_unique_key", "miller", "ppc"]
		):
			tps[(tp.pass_unique_key or "").strip()] = tp
	party_of = {
		key: (resolve_mill_master_name(key, tp.miller) or None, resolve_ppc_master_name(tp.ppc) or None)
		for key, tp in tps.items()
	}
	# only this mill's weighments; its totals then cannot include another mill's records
	wbms = wbms_of_mill([dict(w) for w in wbms], party_of, mill)

	qc_names = sorted({w["quality_check"] for w in wbms if w["quality_check"]})
	qc_bags = (
		{
			qc.name: qc.paddy_received_in_pkt
			for qc in frappe.get_all(
				"Quality Check", filters={"name": ["in", qc_names]}, fields=["name", "paddy_received_in_pkt"]
			)
		}
		if qc_names
		else {}
	)
	names = [w["name"] for w in wbms]
	wbms_with_grn = (
		set(
			frappe.get_all(
				"GRN Note",
				filters={"weigh_bridge_measurement": ["in", names], "docstatus": ["<", 2]},
				pluck="weigh_bridge_measurement",
			)
		)
		if names
		else set()
	)
	# only submitted records of this mill: a draft is not yet a sent entry and a cancelled one is not valid
	sent = frappe.get_all(
		"Gunny Bags Sent to PPC",
		filters={"docstatus": 1, "operating_unit": mill},
		fields=["operating_unit", "ppc", "bags_sent"],
	)
	return build_ledger_rows(
		wbms, qc_bags, wbms_with_grn, tps, party_of=party_of, sent=sent, names_for=_names_for, mill_name=mill_full_name(mill)
	)
