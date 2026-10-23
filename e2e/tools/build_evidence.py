# Copyright (c) 2026, Profezzo and contributors
"""Build the evidence pack of a full E2E run (read-only).

Reads plan.json, ledger.jsonl and checks.jsonl from the run folder, re-reads every created record
from the site, recomputes expected report values independently from source records, runs the four
reports and writes CSV/markdown evidence. Writes nothing to the site.

Usage (from the bench's sites folder):
  ../env/bin/python ../apps/ivri_od/e2e/tools/build_evidence.py <site> <evidence_dir> <backup_prefix>
"""

import csv
import json
import os
import sys
from collections import defaultdict

import frappe
from frappe.utils import flt

TOL = 0.30  # Chhatni tolerance in percentage points (grn_tp_fulfillment.CHHATNI_TOLERANCE_PCT)


def jsonl(path):
	if not os.path.exists(path):
		return []
	with open(path) as f:
		return [json.loads(line) for line in f if line.strip()]


def write_csv(path, header, rows):
	with open(path, "w", newline="") as f:
		w = csv.writer(f)
		w.writerow(header)
		w.writerows(rows)


def band_status(tp_qty, received_pct, assigned):
	"""Mandi Book chhatni status from saved Chhatni records (independent restatement of the rule)."""
	if flt(tp_qty) <= 0:
		return "Chhatni Not Received"
	if flt(assigned) <= 0:
		return "Chhatni Pending"
	if flt(received_pct, 4) > flt(assigned + TOL, 4) + 1e-6:
		return "Extra Chhatni Received"
	if flt(received_pct, 4) >= flt(assigned - TOL, 4) - 1e-6:
		return "Chhatni Received"
	return "Chhatni Pending"


def main(site, run_dir, backup_prefix):
	frappe.init(site=site, sites_path=".")
	frappe.connect()
	try:
		frappe.set_user("Administrator")
		from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
		from ivri_od.procurement.report.abstract_physical.abstract_physical import execute as abstract_physical
		from ivri_od.procurement.report.abstract_report.abstract_report import execute as abstract_report
		from ivri_od.procurement.report.entry_report.entry_report import execute as entry_report
		from ivri_od.procurement.report.mandi_book.mandi_book import execute as mandi_book
		from ivri_od.procurement.transit_pass_resolve import resolve_ppc_master_name

		plan = json.load(open(os.path.join(run_dir, "plan.json")))
		run_id = plan["run_id"]
		ledger = jsonl(os.path.join(run_dir, "ledger.jsonl"))
		checks = jsonl(os.path.join(run_dir, "checks.jsonl"))

		# ---- record_ledger.csv: every created document, re-read from the site
		ledger_rows = []
		created = [r for r in ledger if r.get("name")]
		for r in ledger:
			exists = bool(r.get("name")) and bool(frappe.db.exists(r["doctype"], r["name"]))
			ledger_rows.append([
				r.get("test_id", ""), r["step"], r.get("doctype", ""), r.get("name", ""), "yes" if exists else "no",
				r.get("tp_no", ""), r.get("pass_unique_key", ""), r.get("ppc", ""), r.get("season", ""), r.get("status", ""),
				r.get("net_qt", ""), r.get("chhatni_qt", ""), r.get("received_pct", ""), r.get("entry_quantity", ""),
				r.get("vehicle_no", ""), r.get("error", ""), r.get("at", ""),
			])
		write_csv(os.path.join(run_dir, "record_ledger.csv"),
		          ["test_id", "step", "doctype", "document_name", "exists_now", "tp_no", "pass_unique_key", "ppc", "season",
		           "status", "net_qt", "chhatni_qt", "received_chhatni_pct", "entry_qty", "vehicle_no", "error", "logged_at"],
		          ledger_rows)

		# ---- independent per-pass values from source records
		mb_rows = {r["pass_unique_key"]: r for r in mandi_book({})[1] if r.get("pass_unique_key")}
		per_pass = {}
		for tp in plan["tps"]:
			key = tp["pass_unique_key"]
			grns = frappe.get_all("GRN Note", filters={"pass_unique_key": key, "docstatus": ["<", 2], "is_local_procurement": 0},
			                      fields=["name", "net_weight", "chhatni", "tp_fulfillment_status"])
			received = flt(sum(flt(g.net_weight) for g in grns), 3)
			wbm_net = flt(sum(flt(w) for w in frappe.get_all("Weigh Bridge Measurement", filters={"pass_unique_key": key}, pluck="net_weight")), 3)
			chh = frappe.get_all("Chhatni", filters={"pass_unique_key": key}, fields=["chhatni_qt", "received_chhatni_pct"])
			chhatni_qt = flt(sum(flt(c.chhatni_qt) for c in chh), 3)
			received_pct = flt(sum(flt(c.received_chhatni_pct) for c in chh), 2)
			assigned = max([flt(g.chhatni) for g in grns] or [0.0])
			per_pass[key] = dict(
				tp=tp, grns=len(grns), received=received, wbm_net=wbm_net, chhatni_qt=chhatni_qt, received_pct=received_pct,
				assigned=assigned, pending=flt(max(tp["tp_quantity"] - received, 0), 3),
				excess=flt(max(received - tp["tp_quantity"] - chhatni_qt, 0), 3),
				status=band_status(tp["tp_quantity"], received_pct, assigned),
			)

		recon = []

		def add(report, key_label, field, expected, actual, how, note=""):
			if isinstance(expected, (int, float)) and actual is not None and actual != "":
				ok = abs(flt(expected) - flt(actual)) < 0.0005
				variance = flt(flt(actual) - flt(expected), 3)
			else:
				ok, variance = expected == actual, ""
			recon.append([report, key_label, field, expected, actual, variance, "PASS" if ok else "FAIL", how, note])

		# 1. Mandi Book (one row per pass)
		for key, v in per_pass.items():
			label = f'{v["tp"]["id"]} TP {v["tp"]["tp_no"]} {v["tp"]["ppc_on_pass"]} {v["tp"]["season"]}'
			row = mb_rows.get(key)
			if not row:
				add("Mandi Book", label, "row present", "yes", "no", "GRN Notes exist for the pass" if v["grns"] else "no GRN", "")
				continue
			add("Mandi Book", label, "TP Qty", v["tp"]["tp_quantity"], row["tp_quantity"], "PPAS Transit Pass.quantity")
			add("Mandi Book", label, "Total Qty Received", v["received"], row["total_received"], "sum GRN net_weight of the pass")
			add("Mandi Book", label, "Pending Qty", v["pending"], row["pending_qty"], "max(TP - received, 0)")
			add("Mandi Book", label, "Excess Received Qty", v["excess"], row["excess_received_qty"], "max(received - TP - Chhatni QT, 0)")
			add("Mandi Book", label, "Received Chhatni %", v["received_pct"], row["actual_chhatni_pct"], "Chhatni.received_chhatni_pct (QT / TP x 100)")
			add("Mandi Book", label, "Chhatni Status", v["status"], row["chhatni_status"],
			    f"assigned {v['assigned']}% +/- {TOL} points vs received %")

		# 2. Entry Report (one row per Entry)
		er_rows = entry_report({})[1]
		for r in [x for x in created if x["doctype"] == "Entry"]:
			e = frappe.get_doc("Entry", r["name"])
			match = [x for x in er_rows if str(x.get("tp_no")) == str(e.tp_no) and flt(x.get("entry_qty")) == flt(e.entry_quantity)
			         and (resolve_season_master_name(x.get("season")) or x.get("season")) == e.season]
			label = f'{r["test_id"]} Entry {e.name} TP {e.tp_no}'
			if not match:
				add("Entry Report", label, "row present", "yes", "no", "Entry record")
				continue
			row = match[0]
			add("Entry Report", label, "Entry Qty", flt(e.entry_quantity, 3), row.get("entry_qty"), "Entry.entry_quantity")
			add("Entry Report", label, "Entry Price", flt(e.entry_price_per_quintal, 2), row.get("entry_price"), "Entry.entry_price_per_quintal")
			add("Entry Report", label, "Total Amount", flt(e.total_amount, 2), row.get("total_amount"), "qty x price")
			add("Entry Report", label, "TP Qty", flt(e.tp_quantity, 3), row.get("tp_qty"), "Entry.tp_quantity (from Transit Pass)")

		# 3/4. Abstract Physical and Abstract Report (Season + PPC; only PPCs in PPC Master with a target)
		ap_rows = {(r["season"], r["ppc_name"]): r for r in abstract_physical({})[1]}
		ar_rows = {(r["season"], r["ppc_name"]): r for r in abstract_report({})[1]}
		groups = sorted({(tp["season"], tp["ppc_code"]) for tp in plan["tps"] if tp["ppc_code"]})
		all_tps = frappe.get_all("PPAS Transit Pass", fields=["pass_unique_key", "season", "ppc", "quantity"])
		for season, ppc in groups:
			label = f"{season} {ppc}"
			passes = [t for t in all_tps if resolve_season_master_name(t.season) == season and resolve_ppc_master_name(t.ppc) == ppc]
			keys = [t.pass_unique_key for t in passes]
			tp_total = flt(sum(flt(t.quantity) for t in passes), 3)
			grns = frappe.get_all("GRN Note", filters={"pass_unique_key": ["in", keys or ["-"]], "docstatus": ["<", 2], "is_local_procurement": 0},
			                      fields=["name", "pass_unique_key", "net_weight", "received_quantity"])
			physical = flt(sum(flt(g.net_weight) for g in grns), 3)
			entry_qty = flt(sum(flt(q) for q in frappe.get_all(
				"GRN Entry Detail", filters={"parent": ["in", [g.name for g in grns] or ["-"]], "parenttype": "GRN Note"},
				pluck="entry_quantity")), 3)
			chhatni_qt = flt(sum(flt(q) for q in frappe.get_all("Chhatni", filters={"season": season, "ppc_name": ppc}, pluck="chhatni_qt")), 3)
			denom = tp_total - entry_qty
			pct = flt(chhatni_qt / denom * 100, 2) if denom > 0 else 0.0
			target = flt(sum(flt(t) for t in frappe.get_all("Target Allocation", filters={"season": season, "ppc_name": ppc}, pluck="target_quantity")), 3)
			row = ap_rows.get((season, ppc))
			if not row:
				note = "No Target Allocation > 0 for this PPC and season: the report lists only targeted PPCs (by design)."
				add("Abstract Physical", label, "row present", "yes" if target > 0 else "no", "no", "Target Allocation > 0", note)
			else:
				add("Abstract Physical", label, "TP Quantity", tp_total, row["tp_quantity"], "sum quantity of all Transit Passes of PPC+season")
				add("Abstract Physical", label, "Physical Paddy", physical, row["physical_paddy"], "sum GRN net_weight")
				add("Abstract Physical", label, "Entry Qty", entry_qty, row["entry_qty"], "sum GRN Entry Detail entry_quantity")
				add("Abstract Physical", label, "Chhatni Quantity", chhatni_qt, row["chhatni_quantity"], "sum Chhatni.chhatni_qt by Season+PPC")
				add("Abstract Physical", label, "Chhatni %", pct, row["chhatni_pct"], "Chhatni QT / (TP Qty - Entry Qty) x 100")
			ar = ar_rows.get((season, ppc))
			if not ar:
				add("Abstract Report", label, "row present", "yes" if target > 0 else "no", "no", "Target Allocation > 0",
				    "Report lists only PPCs with a target (by design)." if target <= 0 else "")
			else:
				received = 0.0
				for t in passes:
					g_recv = sum(flt(g.received_quantity) or flt(g.net_weight) for g in grns if g.pass_unique_key == t.pass_unique_key)
					w_net = sum(flt(w) for w in frappe.get_all("Weigh Bridge Measurement", filters={"pass_unique_key": t.pass_unique_key, "is_farmer_or_agent": 0}, pluck="net_weight"))
					received += min(max(g_recv, w_net), flt(t.quantity)) if flt(t.quantity) > 0 else max(g_recv, w_net)
				add("Abstract Report", label, "Total Target", target, ar.get("total_target"), "sum Target Allocation.target_quantity")
				add("Abstract Report", label, "Total Received", flt(received, 3), ar.get("total_received"),
				    "per pass min(max(GRN received, WBM net), TP qty), summed", "Capped at TP qty: excess is not counted (differs from Mandi Book by design).")
				add("Abstract Report", label, "Total Balance", flt(target - received, 3), ar.get("total_balance"), "target - received")

		write_csv(os.path.join(run_dir, "report_reconciliation.csv"),
		          ["report", "row", "field", "expected_from_source_records", "report_value", "variance", "result", "how_expected_was_computed", "note"],
		          recon)

		# ---- expected_vs_actual.csv: browser-run checks + Mandi Book scenario expectations
		eva = [[c["test_id"], c["check"], c["expected"], c["actual"], "", "PASS" if c["pass"] else "FAIL", c.get("detail", "")] for c in checks]
		for key, v in per_pass.items():
			row = mb_rows.get(key) or {}
			for field, exp, act in (("Pending Qty", v["pending"], row.get("pending_qty")),
			                        ("Excess Received Qty", v["excess"], row.get("excess_received_qty")),
			                        ("Chhatni Status", v["status"], row.get("chhatni_status"))):
				ok = (abs(flt(exp) - flt(act)) < 0.0005) if isinstance(exp, float) else exp == act
				var = flt(flt(act) - flt(exp), 3) if isinstance(exp, float) and act is not None else ""
				eva.append([v["tp"]["id"], f"Mandi Book {field} ({v['tp']['scenario']})", exp, act, var, "PASS" if ok else "FAIL",
				            f"received {v['received']} / TP {v['tp']['tp_quantity']} / chhatni {v['chhatni_qt']} QT {v['received_pct']}% vs assigned {v['assigned']}%"])
		write_csv(os.path.join(run_dir, "expected_vs_actual.csv"),
		          ["test_id", "check", "expected", "actual", "variance", "result", "calculation_or_detail"], eva)

		summary = dict(
			created=len(created), failed_steps=[r for r in ledger if str(r.get("status", "")).startswith("FAILED")],
			checks_pass=sum(1 for e in eva if e[5] == "PASS"), checks_fail=[e for e in eva if e[5] != "PASS"],
			recon_pass=sum(1 for r in recon if r[6] == "PASS"), recon_fail=[r for r in recon if r[6] != "PASS"],
			by_doctype=defaultdict(int),
		)
		for r in created:
			summary["by_doctype"][r["doctype"]] += 1
		with open(os.path.join(run_dir, "summary.json"), "w") as f:
			json.dump({k: v for k, v in summary.items()}, f, indent=1, default=str)
		print(json.dumps({"created": summary["created"], "by_doctype": dict(summary["by_doctype"]),
		                  "checks_pass": summary["checks_pass"], "checks_fail": len(summary["checks_fail"]),
		                  "recon_pass": summary["recon_pass"], "recon_fail": len(summary["recon_fail"]),
		                  "failed_steps": len(summary["failed_steps"])}, indent=1))
	finally:
		frappe.db.rollback()
		frappe.destroy()


if __name__ == "__main__":
	main(*sys.argv[1:4])
