# Copyright (c) 2026, Profezzo and contributors
"""Plan a full procurement E2E run (read-only).

Reads the selected PPAS Transit Passes and their assigned Chhatni from the site and writes
plan.json + test_manifest.csv into the run's evidence folder. Writes nothing to the site.

Usage (from the bench's sites folder):
  ../env/bin/python ../apps/ivri_od/e2e/tools/plan_full_run.py <site> <run_id> <evidence_dir>
"""

import csv
import json
import os
import sys

import frappe
from frappe.utils import flt

# (season text on the pass, TP No, PPC name prefix, scenario). Real Transit Passes, chosen in the audit.
SELECTION = [
	("Kharif(2025)", "39", "AGALPUR", "two_grns_full_chhatni_at_assigned"),
	("Kharif(2025)", "137", "BADIMUNDA", "partial_receipt_with_entry"),
	("Kharif(2025)", "46", "BAKTI", "excess_over_tp_with_chhatni"),
	("Kharif(2025)", "15", "BALDHA", "chhatni_assigned_plus_0_3"),
	("Kharif(2025)", "151", "DHANDAMUNDA", "chhatni_assigned_minus_0_3"),
	("Kharif(2025)", "10", "DHOLMANDAL", "chhatni_below_tolerance"),
	("Kharif(2025)", "120", "DUDUKA", "chhatni_above_tolerance"),
	("Rabi(2025)", "196", "BADAJEONA", "partial_receipt_ppc_not_in_master"),
	("Rabi(2025)", "10", "BARAPUDGIA", "three_grns_full_chhatni_at_assigned"),
	("Rabi(2025)", "36", "BATASANA", "qc_mixed_old_new_jute_plastic"),
	("Rabi(2025)", "3", "BHAINSA", "qc_old_jute_only"),
	("Rabi(2025)", "5", "BHALUMUNDA", "qc_new_plastic_only_gunny_gross"),
	("Rabi(2025)", "40", "BHANSULI", "gunny_cut_and_deduction"),
	("Rabi(2025)", "295", "BOBEYA", "duplicate_grn_prevention"),
	("Kharif(2025)", "18", "G S DUNGURIPALI", "same_tp_two_seasons_kharif"),
	("Rabi(2025)", "18", "G S DUNGURIPALI", "same_tp_two_seasons_rabi_with_entry"),
	("Rabi(2025)", "12", "LATHOR", "smallest_tp_full"),
	("Rabi(2025)", "42", "GHUMAR", "three_grns_full_largest_tp"),
]
TARE_QT = 100.0
# RST Date & Time inside each season's Start/End Date, so Season Code and RST Unique Key apply.
RST_DATETIME = {"K": "2026-03-15 10:00:00", "R": "2025-07-15 10:00:00"}
ENTRY_AGENT = "Arjun"  # real Agent Master / Target Allocation agent
ENTRY_PRICE = 2300.0


def truck(net, gunny=0.0, deduction=0.0, old=0, new=0, jute=0, plastic=0):
	return {
		"load_qt": flt(net + TARE_QT + gunny + deduction, 3),
		"tare_qt": TARE_QT,
		"gunny_qt": gunny,
		"deduction_qt": deduction,
		"expected_net_qt": flt(net, 3),
		"old_bags": old,
		"new_bags": new,
		"jute_bags": jute,
		"plastic_bags": plastic,
	}


def bags(qty_qt, kind="mixed"):
	"""About 2 bags per quintal, split by the scenario's bag type."""
	total = max(int(round(qty_qt * 2)), 1)
	half = total // 2
	return {
		"mixed": dict(old=half, new=total - half, jute=half, plastic=total - half),
		"old_jute": dict(old=total, jute=total),
		"new_plastic": dict(new=total, plastic=total),
	}[kind]


def trucks_for(scenario, qty):
	q = flt(qty, 3)
	plans = {
		"two_grns_full_chhatni_at_assigned": [120.0, flt(q - 120, 3)],
		"partial_receipt_with_entry": [100.0],
		"partial_receipt_ppc_not_in_master": [150.0],
		"excess_over_tp_with_chhatni": [260.0],
		"three_grns_full_chhatni_at_assigned": [70.0, 70.0, flt(q - 140, 3)],
		"three_grns_full_largest_tp": [200.0, 200.0, flt(q - 400, 3)],
		"qc_mixed_old_new_jute_plastic": [200.0],
		"gunny_cut_and_deduction": [200.0],
		"same_tp_two_seasons_kharif": [150.0],
	}
	nets = plans.get(scenario, [q])
	kind = {"qc_old_jute_only": "old_jute", "qc_new_plastic_only_gunny_gross": "new_plastic"}.get(scenario, "mixed")
	out = []
	for net in nets:
		extra = {"gunny": 1.5, "deduction": 2.0} if scenario == "gunny_cut_and_deduction" else {}
		out.append(truck(net, **extra, **bags(net, kind)))
	return out


def chhatni_rate_for(scenario, assigned):
	offsets = {
		"two_grns_full_chhatni_at_assigned": 0.0,
		"three_grns_full_chhatni_at_assigned": 0.0,
		"excess_over_tp_with_chhatni": 0.0,
		"chhatni_assigned_plus_0_3": 0.30,
		"chhatni_assigned_minus_0_3": -0.30,
		"chhatni_below_tolerance": -0.31,
		"chhatni_above_tolerance": 0.31,
	}
	if scenario not in offsets or assigned <= 0:
		return None
	return flt(assigned + offsets[scenario], 2)


def main(site, run_id, evidence_dir):
	frappe.init(site=site, sites_path=".")
	frappe.connect()
	try:
		from ivri_od.procurement.doctype.season_mapping.season_mapping import get_chhatni_from_season_mapping
		from ivri_od.procurement.doctype.season_master.season_master import get_season_code, resolve_season_master_name
		from ivri_od.procurement.transit_pass_resolve import mill_id_from_transit_pass, resolve_ppc_master_name

		tps = []
		for idx, (season_text, tp_no, ppc_prefix, scenario) in enumerate(SELECTION, start=1):
			row = frappe.db.sql(
				"""SELECT transit_pass_no, ppc, season, quantity, bags, vehicle_no, pass_unique_key, miller
				FROM `tabPPAS Transit Pass` WHERE season=%s AND transit_pass_no=%s AND ppc LIKE %s""",
				(season_text, tp_no, ppc_prefix + "(%"),
				as_dict=True,
			)[0]
			season = resolve_season_master_name(row.season)
			ppc_code = resolve_ppc_master_name(row.ppc)
			ppc_master = frappe.db.get_value("PPC Master", ppc_code, ["ppc_name", "code"], as_dict=True) if ppc_code else None
			# Many Rabi PPCs are not in PPC Master: use the pass's own NAME(CODE) as Party Name.
			mill = mill_id_from_transit_pass(row)
			assigned = flt(get_chhatni_from_season_mapping(season, ppc_code, mill))
			code = get_season_code(season)
			tid = f"T{idx:02d}"
			plan = {
				"id": tid,
				"scenario": scenario,
				"season": season,
				"season_text": row.season,
				"season_code": code,
				"tp_no": row.transit_pass_no,
				"ppc_on_pass": row.ppc,
				"ppc_code": ppc_code if ppc_master else None,
				"ppc_in_master": bool(ppc_master),
				"party_name": f"{ppc_master.ppc_name}({ppc_master.code})" if ppc_master else row.ppc,
				"pass_unique_key": row.pass_unique_key,
				"tp_quantity": flt(row.quantity, 3),
				"tp_bags": row.bags,
				"tp_vehicle_no": row.vehicle_no,
				"mill": mill,
				"assigned_chhatni_pct": assigned,
				"rst_datetime": RST_DATETIME[code[0]],
				"trucks": [
					dict(t, vehicle_no=f"{run_id}-{tid}{chr(65 + n)}", rst_no=f"{run_id}-{tid}{chr(65 + n)}")
					for n, t in enumerate(trucks_for(scenario, row.quantity))
				],
				"chhatni_rate": chhatni_rate_for(scenario, assigned),
				# Entry needs a PPC Master link; it is saved before the GRNs (Entry checks TP - entries - GRN net).
				"entry": (
					{"agent_name": ENTRY_AGENT, "quantity": 50.0, "price": ENTRY_PRICE}
					if scenario in ("partial_receipt_with_entry", "same_tp_two_seasons_rabi_with_entry") and ppc_master
					else None
				),
				"duplicate_grn_check": scenario == "duplicate_grn_prevention",
			}
			tps.append(plan)

		agalpur = tps[0]
		rst_status_cases = [
			{"id": "S2", "expected": "TP No Not Received", "party_name": agalpur["party_name"], "tp_no": ""},
			{"id": "S3", "expected": "PPC Mismatch", "party_name": tps[2]["party_name"], "tp_no": agalpur["tp_no"]},
			{"id": "S4", "expected": "Local Paddy Purchase", "party_name": f"{run_id} Local Party", "tp_no": ""},
			{"id": "S5", "expected": "Invalid TP No", "party_name": agalpur["party_name"], "tp_no": f"{run_id}-NOTP"},
		]
		for case in rst_status_cases:
			case.update(rst_no=f"{run_id}-{case['id']}", vehicle_no=f"{run_id}-{case['id']}", rst_datetime=agalpur["rst_datetime"])

		ta = frappe.db.sql(
			"""SELECT t.name, t.season, t.ppc_name, t.mill_name, t.target_quantity, t.chhatni, COUNT(a.name) AS agents
			FROM `tabTarget Allocation` t JOIN `tabTarget Allocation Agent` a ON a.parent = t.name
			GROUP BY t.name HAVING agents > 1 LIMIT 1""",
			as_dict=True,
		)

		os.makedirs(evidence_dir, exist_ok=True)
		plan_doc = {"run_id": run_id, "site": site, "tps": tps, "rst_status_cases": rst_status_cases,
		            "target_allocation_multi_agent": ta[0] if ta else None}
		with open(os.path.join(evidence_dir, "plan.json"), "w") as f:
			json.dump(plan_doc, f, indent=1, default=str)
		with open(os.path.join(evidence_dir, "test_manifest.csv"), "w", newline="") as f:
			w = csv.writer(f)
			w.writerow(["test_id", "scenario", "tp_no", "ppc", "ppc_in_ppc_master", "season", "tp_quantity_qtl", "tp_bags", "pass_unique_key",
			            "assigned_chhatni_pct", "planned_trucks", "planned_net_qtl", "test_vehicles_and_rst_nos"])
			for t in tps:
				w.writerow([t["id"], t["scenario"], t["tp_no"], t["ppc_on_pass"], t["ppc_in_master"], t["season"], t["tp_quantity"], t["tp_bags"],
				            t["pass_unique_key"], t["assigned_chhatni_pct"], len(t["trucks"]),
				            flt(sum(x["expected_net_qt"] for x in t["trucks"]), 3), " ".join(x["rst_no"] for x in t["trucks"])])
		print(f"plan written: {len(tps)} TPs, {sum(len(t['trucks']) for t in tps)} trucks, {len(rst_status_cases)} RST status cases")
	finally:
		frappe.db.rollback()
		frappe.destroy()


if __name__ == "__main__":
	main(*sys.argv[1:4])
