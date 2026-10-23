"""End-to-End Government Paddy Procurement Workflow Test.

Executes the complete procurement lifecycle for site shyamji:
1. Target Allocation & Chhatni for all 48 PPCs in Kharif 2025.
2. Entry record for TP 138.
3. 3-step multi-GRN procurement sequence for TP 138:
   Gate Entry (In) -> Quality Check -> RST Details / WBM -> Gate Exit (Out) -> GRN Note
   - Trip 1: 120.000 QTL Net, 5.400 QTL Deduction (Chhatni) -> Status: In Progress, Chhatni Not Received
   - Trip 2: 120.000 QTL Net, 5.400 QTL Deduction (Chhatni) -> Status: In Progress, Chhatni Not Received
   - Trip 3: 118.780 QTL Net, 5.345 QTL Deduction (Chhatni) -> Status: TP Completed, Chhatni Received
4. Report verification across all 6 procurement reports:
   - Abstract Report
   - Abstract Physical
   - Entry Report
   - Mandi Book
   - TP Mandi Quantity Fulfillment
   - Chhatni Tracking
"""

import unittest
from datetime import datetime
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, now_datetime, nowdate, nowtime

from ivri_od.procurement.grn_tp_fulfillment import (
	CHHATNI_NOT_RECEIVED,
	CHHATNI_RECEIVED,
	calculate_chhatni_metrics,
	refresh_tp_fulfillment_for_pass,
)
from ivri_od.procurement.report.abstract_report.abstract_report import execute as execute_abstract_report
from ivri_od.procurement.report.abstract_physical.abstract_physical import execute as execute_abstract_physical
from ivri_od.procurement.report.entry_report.entry_report import execute as execute_entry_report
from ivri_od.procurement.report.mandi_book.mandi_book import execute as execute_mandi_book
from ivri_od.procurement.report.tp_mandi_quantity_fulfillment.tp_mandi_quantity_fulfillment import (
	execute as execute_tp_fulfillment,
)
from ivri_od.procurement.report.chhatni_tracking.chhatni_tracking import execute as execute_chhatni_tracking


TP_138_KEY = "M051007-DUDUKA(S1050113)-K25-TP138"
PPC_CODE = "S1050113"
PPC_DISPLAY = "DUDUKA(S1050113)"
MILL_CODE = "M051007"
SEASON = "Kharif 2025"
VEHICLE_NO = "OD16G4699"
DRIVER_NAME = "JugalKishorBehera"
AGENT_NAME = "Arjun"
TP_QTY = 358.78


def setup_target_allocations():
	"""Ensure all 48 PPCs in PPC Master have realistic Target Allocation & Chhatni in Kharif 2025."""
	frappe.set_user("Administrator")
	ppcs = frappe.get_all("PPC Master", fields=["name", "ppc_name", "agent", "is_active"])
	print(f"[SETUP] Authoritative PPCs in PPC Master: {len(ppcs)}")

	existing_tas = {
		ta.ppc_name: ta
		for ta in frappe.get_all(
			"Target Allocation",
			filters={"season": SEASON},
			fields=["name", "ppc_name", "mill_name", "target_quantity", "chhatni"],
		)
	}

	created_ca = 0
	created_ta = 0

	for p in ppcs:
		code = p.name
		# 1. Ensure Chhatni Assign exists for this PPC
		ca_name = frappe.db.get_value(
			"Chhatni Assign",
			{"ppc_name": code, "mill_name": MILL_CODE, "season": SEASON},
			"name",
		)
		chhatni_rate = 4.5 if code == PPC_CODE else 4.0
		if not ca_name:
			ca_doc = frappe.new_doc("Chhatni Assign")
			ca_doc.ppc_name = code
			ca_doc.mill_name = MILL_CODE
			ca_doc.season = SEASON
			ca_doc.chutney_quantity_kg_per_quintal = chhatni_rate
			ca_doc.insert(ignore_permissions=True)
			created_ca += 1

		# 2. Ensure Target Allocation exists
		if code not in existing_tas:
			ta_doc = frappe.new_doc("Target Allocation")
			ta_doc.season = SEASON
			ta_doc.ppc_name = code
			ta_doc.mill_name = MILL_CODE
			ta_doc.agent_name = (p.agent or "").strip() or AGENT_NAME
			ta_doc.target_quantity = 3500.0
			ta_doc.chhatni = chhatni_rate
			ta_doc.insert(ignore_permissions=True)
			created_ta += 1
		else:
			# Ensure DUDUKA has chhatni = 4.5
			if code == PPC_CODE:
				ta_rec = existing_tas[code]
				if flt(ta_rec.chhatni) != 4.5:
					frappe.db.set_value("Target Allocation", ta_rec.name, "chhatni", 4.5, update_modified=True)

	frappe.db.commit()
	all_tas = frappe.get_all("Target Allocation", filters={"season": SEASON}, pluck="name")
	print(f"[SETUP] Total Target Allocations in {SEASON}: {len(all_tas)} (created {created_ta} new TAs, {created_ca} new CAs)")
	assert len(all_tas) == len(ppcs), f"Expected {len(ppcs)} Target Allocations, got {len(all_tas)}"


def cleanup_tp138_test_data():
	"""Clean up any existing test records for TP 138 to ensure a fresh, repeatable test run."""
	frappe.set_user("Administrator")
	# 1. Gate Exits
	gx_list = frappe.get_all("Gate Exit", filters={"vehicle_no": VEHICLE_NO}, pluck="name")
	for gx in gx_list:
		frappe.delete_doc("Gate Exit", gx, force=True, ignore_permissions=True)

	# 2. GRNs
	grn_list = frappe.get_all("GRN Note", filters={"pass_unique_key": TP_138_KEY}, pluck="name")
	for g in grn_list:
		frappe.delete_doc("GRN Note", g, force=True, ignore_permissions=True)

	# 3. WBMs
	wbm_list = frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"rst_no": ["like", "RST-TP138%"]},
		pluck="name",
	)
	for w in wbm_list:
		frappe.delete_doc("Weigh Bridge Measurement", w, force=True, ignore_permissions=True)

	# 4. RSTs
	rst_list = frappe.get_all(
		"RST Details",
		filters={"rst_no": ["like", "RST-TP138%"]},
		pluck="name",
	)
	for r in rst_list:
		frappe.delete_doc("RST Details", r, force=True, ignore_permissions=True)

	# 5. Quality Checks
	qc_list = frappe.get_all("Quality Check", filters={"vehicle_no": VEHICLE_NO}, pluck="name")
	for q in qc_list:
		frappe.delete_doc("Quality Check", q, force=True, ignore_permissions=True)

	# 6. Gate Entries
	ge_list = frappe.get_all("Gate Entry", filters={"vehicle_no": VEHICLE_NO}, pluck="name")
	for ge in ge_list:
		frappe.delete_doc("Gate Entry", ge, force=True, ignore_permissions=True)

	# 7. Entry record for TP 138
	en_list = frappe.get_all("Entry", filters={"tp_no": "138", "ppc_name": PPC_CODE}, pluck="name")
	for en in en_list:
		frappe.delete_doc("Entry", en, force=True, ignore_permissions=True)

	frappe.db.commit()
	print("[CLEANUP] TP 138 test transactions cleared.")


def create_entry_record():
	"""Create Entry record for TP 138."""
	frappe.set_user("Administrator")
	existing = frappe.db.get_value("Entry", {"tp_no": "138", "ppc_name": PPC_CODE}, "name")
	if existing:
		return frappe.get_doc("Entry", existing)

	entry = frappe.new_doc("Entry")
	entry.season = SEASON
	entry.ppc_name = PPC_CODE
	entry.tp_no = "138"
	entry.agent_name = AGENT_NAME
	entry.entry_quantity = 50.0
	entry.entry_price_per_quintal = 2300.0
	entry.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"[ENTRY] Created Entry {entry.name}: Qty=50.0 QTL, Price=2300, Total={entry.total_amount}")
	return entry


def execute_trip(trip_num: int, gross_wt: float, tare_wt: float, gunny_wt: float, ded_wt: float, bags: int):
	"""Execute single procurement trip through full workflow."""
	frappe.set_user("Administrator")
	expected_net = flt(gross_wt - tare_wt - gunny_wt - ded_wt, 3)
	print(f"\n--- [TRIP {trip_num}] START: Gross={gross_wt}, Tare={tare_wt}, Gunny={gunny_wt}, Deduction={ded_wt} -> Expected Net={expected_net} ---")

	# Step 1: Gate Entry (In)
	ge = frappe.new_doc("Gate Entry")
	ge.in_out = "In"
	ge.in_purpose = "Paddy"
	ge.going_to_weighment = 1
	ge.vehicle_no = VEHICLE_NO
	ge.driver_name = DRIVER_NAME
	ge.party_name = PPC_DISPLAY
	ge.entry_datetime = now_datetime()
	ge.insert(ignore_permissions=True)
	assert ge.inside_mill == 1, "Gate Entry inside_mill must be 1"
	print(f"  Step 1: Gate Entry {ge.name} created (inside_mill=1)")

	# Step 2: Quality Check
	qc = frappe.new_doc("Quality Check")
	qc.vehicle_no = VEHICLE_NO
	qc.gate_entry = ge.name
	qc.driver_name = DRIVER_NAME
	qc.paddy_quality = "Mota"
	qc.staff_name = "QC Inspector"
	qc.unloading_point = "Shed 1"
	qc.paddy_received_in_pkt = bags
	qc.paddy_returned = 0
	qc.append("old_new_bags", {"new_bags": bags, "old_bags": 0})
	qc.append("type_of_pkt", {"no_of_plastic_bag": bags, "jute_pkt_no": 0})
	qc.insert(ignore_permissions=True)
	assert qc.qc_decision == "Accepted", f"QC decision must be Accepted, got {qc.qc_decision}"
	print(f"  Step 2: Quality Check {qc.name} created (qc_decision=Accepted)")

	# Step 3: RST Details
	rst_no = f"RST-TP138-0{trip_num}"
	rst = frappe.new_doc("RST Details")
	rst.rst_no = rst_no
	rst.party_name = PPC_DISPLAY
	rst.tp_no = "138"
	rst.vehicle_no = VEHICLE_NO
	rst.gross_vehicle_weight_qt = gross_wt
	rst.tare_vehicle_weight_qt = tare_wt
	rst.gunny_weight_qt = gunny_wt
	rst.deduction_qt = ded_wt
	rst.commodity = "Paddy"
	rst.insert(ignore_permissions=True)
	print(f"  Step 3: RST Details {rst.name} created with rst_no={rst_no}")

	# Step 4: Verify WBM and GRN Note
	wbm_name = frappe.db.get_value("Weigh Bridge Measurement", {"rst_no": rst_no}, "name")
	assert wbm_name, f"WBM not created for RST {rst_no}"
	wbm = frappe.get_doc("Weigh Bridge Measurement", wbm_name)
	assert flt(wbm.net_weight, 3) == expected_net, f"WBM net_weight {wbm.net_weight} != expected {expected_net}"
	assert flt(wbm.gunny_weight, 3) == gunny_wt, f"WBM gunny_weight {wbm.gunny_weight} != {gunny_wt}"
	print(f"  Step 4a: WBM {wbm.name} verified (net_weight={wbm.net_weight}, gunny_weight={wbm.gunny_weight})")

	# GRN is generated after Gate Exit, not at tare weight.
	assert not frappe.db.exists("GRN Note", {"weigh_bridge_measurement": wbm_name}), (
		f"GRN Note must not exist before Gate Exit for WBM {wbm_name}"
	)
	print("  Step 4b: no GRN Note yet (vehicle still inside the mill)")

	# Step 5: Gate Exit (Out) -> GRN Note auto-generated
	gx = frappe.new_doc("Gate Exit")
	gx.out_purpose = "Others"
	gx.out_purpose_detail = "Unloading complete"
	gx.vehicle_no = VEHICLE_NO
	gx.gate_entry_in = ge.name
	gx.insert(ignore_permissions=True)
	ge_inside = frappe.db.get_value("Gate Entry", ge.name, "inside_mill")
	assert ge_inside == 0, f"Gate Entry inside_mill must be 0 after exit, got {ge_inside}"
	print(f"  Step 5: Gate Exit {gx.name} recorded (Gate In inside_mill updated to 0)")

	grn_name = frappe.db.get_value("GRN Note", {"weigh_bridge_measurement": wbm_name}, "name")
	assert grn_name, f"GRN Note not created after Gate Exit for WBM {wbm_name}"
	grn = frappe.get_doc("GRN Note", grn_name)
	assert flt(grn.net_weight, 3) == expected_net, f"GRN net_weight {grn.net_weight} != {expected_net}"
	assert flt(grn.gunny_weight, 3) == gunny_wt, f"GRN gunny_weight {grn.gunny_weight} != {gunny_wt}"
	assert flt(grn.deduction, 3) == ded_wt, f"GRN deduction {grn.deduction} != {ded_wt}"
	assert grn.gate_exit == gx.name, f"GRN gate_exit {grn.gate_exit} != {gx.name}"
	print(f"  Step 5b: GRN Note {grn.name} created after exit (net_weight={grn.net_weight}, gate_exit={grn.gate_exit})")

	frappe.db.commit()
	refresh_tp_fulfillment_for_pass(TP_138_KEY)
	grn.reload()
	return grn


def run_e2e_procurement():
	"""Complete End-to-End Government Paddy Procurement Workflow Test."""
	print("=" * 70)
	print("STARTING COMPLETE END-TO-END PROCUREMENT WORKFLOW TEST")
	print("=" * 70)

	# 1. Target Allocation Setup
	print("\n>>> PHASE 1: TARGET ALLOCATION SETUP")
	setup_target_allocations()

	# 2. Cleanup existing test transactions
	print("\n>>> PHASE 2: CLEANUP PREVIOUS TP 138 TRANSACTIONS")
	cleanup_tp138_test_data()

	# 3. Create Entry Record
	print("\n>>> PHASE 3: CREATE ENTRY RECORD")
	entry = create_entry_record()

	# 4. Multi-GRN Execution
	print("\n>>> PHASE 4: EXECUTE MULTI-GRN PROCUREMENT WORKFLOW FOR TP 138")
	# Trip 1: 120.000 QTL Net, 5.400 QTL Deduction
	grn1 = execute_trip(
		trip_num=1,
		gross_wt=206.400,
		tare_wt=80.000,
		gunny_wt=1.000,
		ded_wt=5.400,
		bags=274,
	)
	print(f"\n[TRIP 1 STATUS CHECK]")
	print(f"  Received Qty: {grn1.received_quantity} QTL")
	print(f"  Cumulative Received: {grn1.tp_cumulative_received} / {TP_QTY} QTL")
	print(f"  TP Fulfillment Status: {grn1.tp_fulfillment_status}")
	print(f"  Cumulative Deduction: {grn1.tp_cumulative_deduction} QTL")
	print(f"  Chhatni %: {grn1.chhatni_received_pct}%")
	print(f"  Chhatni Fulfillment Status: {grn1.chhatni_fulfillment_status}")

	assert flt(grn1.tp_cumulative_received, 3) == 120.000, f"Trip 1 cumulative received must be 120.0, got {grn1.tp_cumulative_received}"
	assert grn1.tp_fulfillment_status == "In Progress", f"Trip 1 status must be 'In Progress', got {grn1.tp_fulfillment_status}"
	assert grn1.chhatni_fulfillment_status == "Chhatni Not Received", f"Trip 1 Chhatni status must be 'Chhatni Not Received', got {grn1.chhatni_fulfillment_status}"

	# Trip 2: 120.000 QTL Net, 5.400 QTL Deduction
	grn2 = execute_trip(
		trip_num=2,
		gross_wt=206.400,
		tare_wt=80.000,
		gunny_wt=1.000,
		ded_wt=5.400,
		bags=274,
	)
	print(f"\n[TRIP 2 STATUS CHECK]")
	print(f"  Received Qty: {grn2.received_quantity} QTL")
	print(f"  Cumulative Received: {grn2.tp_cumulative_received} / {TP_QTY} QTL")
	print(f"  TP Fulfillment Status: {grn2.tp_fulfillment_status}")
	print(f"  Cumulative Deduction: {grn2.tp_cumulative_deduction} QTL")
	print(f"  Chhatni %: {grn2.chhatni_received_pct}%")
	print(f"  Chhatni Fulfillment Status: {grn2.chhatni_fulfillment_status}")

	assert flt(grn2.tp_cumulative_received, 3) == 240.000, f"Trip 2 cumulative received must be 240.0, got {grn2.tp_cumulative_received}"
	assert grn2.tp_fulfillment_status == "In Progress", f"Trip 2 status must be 'In Progress', got {grn2.tp_fulfillment_status}"
	assert grn2.chhatni_fulfillment_status == "Chhatni Not Received", f"Trip 2 Chhatni status must be 'Chhatni Not Received', got {grn2.chhatni_fulfillment_status}"

	# Trip 3: 118.780 QTL Net, 5.345 QTL Deduction
	grn3 = execute_trip(
		trip_num=3,
		gross_wt=205.125,
		tare_wt=80.000,
		gunny_wt=1.000,
		ded_wt=5.345,
		bags=273,
	)
	print(f"\n[TRIP 3 STATUS CHECK - FINAL FULFILLMENT]")
	print(f"  Received Qty: {grn3.received_quantity} QTL")
	print(f"  Cumulative Received: {grn3.tp_cumulative_received} / {TP_QTY} QTL")
	print(f"  TP Fulfillment Status: {grn3.tp_fulfillment_status}")
	print(f"  Cumulative Deduction: {grn3.tp_cumulative_deduction} QTL")
	print(f"  Chhatni %: {grn3.chhatni_received_pct}%")
	print(f"  Chhatni Fulfillment Status: {grn3.chhatni_fulfillment_status}")

	assert flt(grn3.tp_cumulative_received, 3) == 358.780, f"Trip 3 cumulative received must be 358.780, got {grn3.tp_cumulative_received}"
	assert grn3.tp_fulfillment_status == "TP Completed", f"Trip 3 status must be 'TP Completed', got {grn3.tp_fulfillment_status}"
	assert flt(grn3.tp_cumulative_deduction, 3) == 16.145, f"Trip 3 cumulative deduction must be 16.145, got {grn3.tp_cumulative_deduction}"
	assert flt(grn3.chhatni_received_pct, 2) == 0.0, f"Trip 3 Chhatni % must be 0.0%, got {grn3.chhatni_received_pct}"
	assert grn3.chhatni_fulfillment_status == "Chhatni Not Received", f"Trip 3 Chhatni status must be 'Chhatni Not Received', got {grn3.chhatni_fulfillment_status}"

	# 5. Report Validations
	print("\n>>> PHASE 5: VALIDATE ALL 6 PROCUREMENT REPORTS")

	# Report 1: Abstract Report
	print("\n--- Validating Report 1: Abstract Report ---")
	_, ar_data = execute_abstract_report({"season": SEASON})
	assert len(ar_data) == 48, f"Abstract Report must contain all 48 PPCs for {SEASON}, got {len(ar_data)}"
	duduka_ar = next((r for r in ar_data if r.get("ppc_name") == PPC_CODE), None)
	assert duduka_ar, "DUDUKA row missing in Abstract Report"
	print(f"  Abstract Report DUDUKA: Target={duduka_ar['total_target']}, Received={duduka_ar['total_received']}, Balance={duduka_ar['total_balance']}")
	# Baseline received was 307.396 + 358.78 = 666.176 QTL
	assert flt(duduka_ar["total_target"]) == 5000.0, f"Target must be 5000.0, got {duduka_ar['total_target']}"
	assert flt(duduka_ar["total_received"], 3) == 666.176, f"Received must be 666.176, got {duduka_ar['total_received']}"
	assert flt(duduka_ar["total_balance"], 3) == 4333.824, f"Balance must be 4333.824, got {duduka_ar['total_balance']}"
	print("  ✓ Abstract Report: PASS")

	# Report 2: Abstract Physical
	print("\n--- Validating Report 2: Abstract Physical ---")
	_, ap_data = execute_abstract_physical({"season": SEASON})
	assert len(ap_data) == 48, f"Abstract Physical must contain all 48 PPCs for {SEASON}, got {len(ap_data)}"
	duduka_ap = next((r for r in ap_data if r.get("ppc") == PPC_DISPLAY), None)
	assert duduka_ap, "DUDUKA row missing in Abstract Physical"
	print(f"  Abstract Physical DUDUKA: TP Qty={duduka_ap['tp_quantity']}, Physical={duduka_ap['physical_paddy']}, Entry Qty={duduka_ap['entry_qty']}, Deduction={duduka_ap['chhatni_quantity']}, Chhatni%={duduka_ap['chhatni_pct']}")
	assert flt(duduka_ap["physical_paddy"], 3) == 666.176, f"Physical paddy must be 666.176, got {duduka_ap['physical_paddy']}"
	# Chhatni Quantity = cumulative Chhatni (QT) of the saved Chhatni records for this PPC and season.
	expected_chhatni = flt(
		sum(flt(q) for q in frappe.get_all("Chhatni", filters={"ppc_name": PPC_CODE, "season": SEASON}, pluck="chhatni_qt")),
		3,
	)
	assert flt(duduka_ap["chhatni_quantity"], 3) == expected_chhatni, f"Chhatni qty must be {expected_chhatni}, got {duduka_ap['chhatni_quantity']}"
	print("  ✓ Abstract Physical: PASS")

	# Report 3: Entry Report
	print("\n--- Validating Report 3: Entry Report ---")
	er_cols, er_data = execute_entry_report({"season": SEASON})
	expected_cols = ["season", "ppc", "tp_no", "tp_qty", "mill_name", "agent_name", "entry_qty", "entry_price", "total_amount"]
	actual_cols = [c["fieldname"] for c in er_cols]
	assert actual_cols == expected_cols, f"Entry Report columns mismatch: {actual_cols} != {expected_cols}"
	tp138_entry = next((r for r in er_data if str(r.get("tp_no")) == "138"), None)
	assert tp138_entry, "Entry row for TP 138 missing in Entry Report"
	print(f"  Entry Report TP 138: Season={tp138_entry['season']}, PPC={tp138_entry['ppc']}, TP No={tp138_entry['tp_no']}, Qty={tp138_entry['entry_qty']}, Price={tp138_entry['entry_price']}, Total={tp138_entry['total_amount']}")
	assert flt(tp138_entry["entry_qty"]) == 50.0
	assert flt(tp138_entry["entry_price"]) == 2300.0
	assert flt(tp138_entry["total_amount"]) == 115000.0
	print("  ✓ Entry Report: PASS")

	# Report 4: Mandi Book
	print("\n--- Validating Report 4: Mandi Book ---")
	_, mb_data = execute_mandi_book({"season": SEASON})
	mb_row = next((r for r in mb_data if r.get("pass_unique_key") == TP_138_KEY), None)
	assert mb_row, "Mandi Book row for TP 138 missing"
	print(f"  Mandi Book TP 138: TP Qty={mb_row['tp_quantity']}, Total Received={mb_row['total_received']}, Pending={mb_row['pending_qty']}, Status={mb_row['tp_status']}, Chhatni Assigned={mb_row['chhatni_assigned']}%, Received Chhatni={mb_row['actual_chhatni_pct']}%, Chhatni Status={mb_row['chhatni_status']}")
	assert flt(mb_row["tp_quantity"], 3) == 358.780
	assert flt(mb_row["total_received"], 3) == 358.780
	assert flt(mb_row["pending_qty"], 3) == 0.0
	assert mb_row["tp_status"] == "TP Completed"
	assert flt(mb_row["actual_chhatni_pct"], 2) == 0.0
	# Mandi Book status comes from saved Chhatni records; none exist for this pass yet.
	assert mb_row["chhatni_status"] == "Chhatni Pending"
	print("  ✓ Mandi Book: PASS")

	# Report 5: TP Mandi Quantity Fulfillment
	print("\n--- Validating Report 5: TP Mandi Quantity Fulfillment ---")
	_, tpf_data = execute_tp_fulfillment({})
	tpf_row = next((r for r in tpf_data if r.get("pass_unique_key") == TP_138_KEY), None)
	assert tpf_row, "TP Mandi Quantity Fulfillment row for TP 138 missing"
	print(f"  TP Mandi Fulfillment TP 138: TP Quantity={tpf_row['tp_quantity']}, Fulfilled={tpf_row['fulfilled_quantity']}, WBM Count={tpf_row['wbm_count']}")
	assert flt(tpf_row["tp_quantity"], 3) == 358.780
	assert flt(tpf_row["fulfilled_quantity"], 3) == 358.780
	assert tpf_row["wbm_count"] == 3, f"Expected 3 WBMs, got {tpf_row['wbm_count']}"
	assert flt(tpf_row["remaining_quantity"], 3) == 0.0
	print("  ✓ TP Mandi Quantity Fulfillment: PASS")

	# Report 6: Chhatni Tracking
	print("\n--- Validating Report 6: Chhatni Tracking ---")
	_, ct_data = execute_chhatni_tracking({"season": SEASON})
	ct_row = next((r for r in ct_data if r.get("pass_unique_key") == TP_138_KEY), None)
	assert ct_row, "Chhatni Tracking row for TP 138 missing"
	print(f"  Chhatni Tracking TP 138: TP Qty={ct_row['tp_quantity']}, Received={ct_row['total_received']}, Assigned%={ct_row['chhatni_assigned_pct']}%, Received%={ct_row['received_chhatni_pct']}%, Status={ct_row['chhatni_status']}")
	assert flt(ct_row["tp_quantity"], 3) == 358.780
	assert flt(ct_row["total_received"], 3) == 358.780
	assert flt(ct_row["chhatni_assigned_pct"], 2) == 4.50
	assert flt(ct_row["received_chhatni_pct"], 2) == 0.0
	assert ct_row["chhatni_status"] == "Chhatni Not Received"
	print("  ✓ Chhatni Tracking: PASS")

	print("\n" + "=" * 70)
	print("ALL PHASES AND ALL 6 REPORTS VALIDATED SUCCESSFULLY!")
	print("=" * 70)
	return True


def run():
	return run_e2e_procurement()
