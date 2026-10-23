"""Comprehensive tests for TP fulfillment and cumulative received quantity."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from ivri_od.procurement.grn_tp_fulfillment import (
	CHHATNI_NOT_RECEIVED,
	CHHATNI_RECEIVED,
	EXTRA_CHHATNI_RECEIVED,
	calculate_chhatni_metrics,
	evaluate_chhatni_fulfillment,
	excess_tp_received_quantity,
	grn_received_quantity,
	pending_tp_quantity,
	received_chhatni_pct,
	remaining_tp_quantity,
	required_chhatni_qt,
	tp_fulfillment_status,
	calculate_tp_status_for_pass,
)
from ivri_od.procurement.report.mandi_book.mandi_book import execute as execute_mandi_book, get_columns


class TestTPFulfillment(FrappeTestCase):
	def test_tp_status_zero_net_weight_is_pending(self):
		"""Total net weight = 0 QTL -> Pending."""
		self.assertEqual(tp_fulfillment_status(250.0, 0.0), "Pending")
		self.assertEqual(tp_fulfillment_status(0.0, 0.0), "Pending")

	def test_tp_status_100_of_250_is_in_progress(self):
		"""Total net weight = 100 QTL, TP quantity = 250 QTL -> In Progress."""
		self.assertEqual(tp_fulfillment_status(250.0, 100.0), "In Progress")

	def test_tp_status_250_of_250_is_tp_completed(self):
		"""Total net weight = 250 QTL, TP quantity = 250 QTL -> TP Completed."""
		self.assertEqual(tp_fulfillment_status(250.0, 250.0), "TP Completed")

	def test_tp_status_275_of_250_is_tp_completed(self):
		"""Total net weight = 275 QTL, TP quantity = 250 QTL -> TP Completed."""
		self.assertEqual(tp_fulfillment_status(250.0, 275.0), "TP Completed")

	def test_tp_status_missing_or_zero_tp_quantity_safe(self):
		"""Handle missing or zero TP quantity safely without division errors or incorrect completion."""
		self.assertEqual(tp_fulfillment_status(0.0, 0.0), "Pending")
		self.assertEqual(tp_fulfillment_status(0.0, 100.0), "In Progress")
		self.assertEqual(tp_fulfillment_status(-50.0, 100.0), "In Progress")

	def test_calculate_tp_status_for_pass_qualifying_grns(self):
		"""Test calculate_tp_status_for_pass aggregates valid submitted GRNs and excludes draft/cancelled."""
		test_key = "TEST-TP-KEY-STATUS-AUDIT-999"
		test_tp_qty = 250.0

		created_docs = []
		try:
			# Mock / set up TP record
			tp_doc = frappe.new_doc("PPAS Transit Pass")
			tp_doc.pass_unique_key = test_key
			tp_doc.quantity = test_tp_qty
			tp_doc.flags.ignore_mandatory = True
			tp_doc.flags.ignore_validate = True
			tp_doc.insert(ignore_permissions=True)
			created_docs.append(("PPAS Transit Pass", tp_doc.name))

			# 1. No GRNs yet -> Pending
			self.assertEqual(calculate_tp_status_for_pass(test_key), "Pending")

			# 2. Add Draft GRN (docstatus = 0, 100 QTL) -> must not contribute, still Pending
			draft_grn = frappe.new_doc("GRN Note")
			draft_grn.pass_unique_key = test_key
			draft_grn.is_local_procurement = 0
			draft_grn.tp_quantity = test_tp_qty
			draft_grn.net_weight = 100.0
			draft_grn.docstatus = 0
			draft_grn.flags.ignore_mandatory = True
			draft_grn.flags.ignore_validate = True
			draft_grn.insert(ignore_permissions=True)
			created_docs.append(("GRN Note", draft_grn.name))

			self.assertEqual(calculate_tp_status_for_pass(test_key), "Pending")

			# 3. Add Cancelled GRN (docstatus = 2, 150 QTL) -> must not contribute, still Pending
			canc_grn = frappe.new_doc("GRN Note")
			canc_grn.pass_unique_key = test_key
			canc_grn.is_local_procurement = 0
			canc_grn.tp_quantity = test_tp_qty
			canc_grn.net_weight = 150.0
			canc_grn.flags.ignore_mandatory = True
			canc_grn.flags.ignore_validate = True
			canc_grn.insert(ignore_permissions=True)
			frappe.db.set_value("GRN Note", canc_grn.name, "docstatus", 2)
			created_docs.append(("GRN Note", canc_grn.name))

			self.assertEqual(calculate_tp_status_for_pass(test_key), "Pending")

			# 4. Add First Submitted GRN (docstatus = 1, 100 QTL) -> In Progress (100 / 250)
			sub1_grn = frappe.new_doc("GRN Note")
			sub1_grn.pass_unique_key = test_key
			sub1_grn.is_local_procurement = 0
			sub1_grn.tp_quantity = test_tp_qty
			sub1_grn.net_weight = 100.0
			sub1_grn.flags.ignore_mandatory = True
			sub1_grn.flags.ignore_validate = True
			sub1_grn.insert(ignore_permissions=True)
			frappe.db.set_value("GRN Note", sub1_grn.name, "docstatus", 1)
			created_docs.append(("GRN Note", sub1_grn.name))

			self.assertEqual(calculate_tp_status_for_pass(test_key), "In Progress")

			# 5. Add Second Submitted GRN (docstatus = 1, 150 QTL) -> TP Completed (100 + 150 = 250 / 250)
			sub2_grn = frappe.new_doc("GRN Note")
			sub2_grn.pass_unique_key = test_key
			sub2_grn.is_local_procurement = 0
			sub2_grn.tp_quantity = test_tp_qty
			sub2_grn.net_weight = 150.0
			sub2_grn.flags.ignore_mandatory = True
			sub2_grn.flags.ignore_validate = True
			sub2_grn.insert(ignore_permissions=True)
			frappe.db.set_value("GRN Note", sub2_grn.name, "docstatus", 1)
			created_docs.append(("GRN Note", sub2_grn.name))

			self.assertEqual(calculate_tp_status_for_pass(test_key), "TP Completed")

			# 6. Add Third Submitted GRN (docstatus = 1, 25 QTL) -> TP Completed (275 >= 250)
			sub3_grn = frappe.new_doc("GRN Note")
			sub3_grn.pass_unique_key = test_key
			sub3_grn.is_local_procurement = 0
			sub3_grn.tp_quantity = test_tp_qty
			sub3_grn.net_weight = 25.0
			sub3_grn.flags.ignore_mandatory = True
			sub3_grn.flags.ignore_validate = True
			sub3_grn.insert(ignore_permissions=True)
			frappe.db.set_value("GRN Note", sub3_grn.name, "docstatus", 1)
			created_docs.append(("GRN Note", sub3_grn.name))

			self.assertEqual(calculate_tp_status_for_pass(test_key), "TP Completed")
		finally:
			for dt, dn in reversed(created_docs):
				frappe.delete_doc(dt, dn, force=True, ignore_permissions=True)

	def test_edge_case_1_300_vs_288(self):
		"""TP = 300, Net received = 288 -> In Progress, Pending = 12, Excess = 0."""
		tp_qty = 300.0
		net_received = 288.0
		self.assertEqual(tp_fulfillment_status(tp_qty, net_received), "In Progress")
		self.assertEqual(remaining_tp_quantity(tp_qty, net_received), 12.0)
		self.assertEqual(pending_tp_quantity(tp_qty, net_received), 12.0)
		self.assertEqual(excess_tp_received_quantity(tp_qty, net_received), 0.0)

	def test_edge_case_2_299_999(self):
		"""TP = 300, Net received = 299.999 -> In Progress, Pending > 0, Excess = 0."""
		tp_qty = 300.0
		net_received = 299.999
		self.assertEqual(tp_fulfillment_status(tp_qty, net_received), "In Progress")
		self.assertEqual(remaining_tp_quantity(tp_qty, net_received), 0.001)
		self.assertEqual(pending_tp_quantity(tp_qty, net_received), 0.001)
		self.assertEqual(excess_tp_received_quantity(tp_qty, net_received), 0.0)

	def test_edge_case_3_300_exact(self):
		"""TP = 300, Net received = 300 -> TP Completed, Pending = 0, Excess = 0."""
		tp_qty = 300.0
		net_received = 300.0
		self.assertEqual(tp_fulfillment_status(tp_qty, net_received), "TP Completed")
		self.assertEqual(remaining_tp_quantity(tp_qty, net_received), 0.0)
		self.assertEqual(pending_tp_quantity(tp_qty, net_received), 0.0)
		self.assertEqual(excess_tp_received_quantity(tp_qty, net_received), 0.0)

	def test_edge_case_4_301_overfill(self):
		"""TP = 300, Net received = 301 -> TP Completed, Pending = 0, Excess = 1."""
		tp_qty = 300.0
		net_received = 301.0
		self.assertEqual(tp_fulfillment_status(tp_qty, net_received), "TP Completed")
		self.assertEqual(remaining_tp_quantity(tp_qty, net_received), 0.0)
		self.assertEqual(pending_tp_quantity(tp_qty, net_received), 0.0)
		self.assertEqual(excess_tp_received_quantity(tp_qty, net_received), 1.0)

	def test_case_5_200_vs_250_extra(self):
		"""TP = 200, Net received = 250 -> TP Completed, Pending = 0, Excess = 50."""
		tp_qty = 200.0
		net_received = 250.0
		self.assertEqual(tp_fulfillment_status(tp_qty, net_received), "TP Completed")
		self.assertEqual(pending_tp_quantity(tp_qty, net_received), 0.0)
		self.assertEqual(excess_tp_received_quantity(tp_qty, net_received), 50.0)

	def test_case_6_200_vs_180_short(self):
		"""TP = 200, Net received = 180 -> In Progress, Pending = 20, Excess = 0."""
		tp_qty = 200.0
		net_received = 180.0
		self.assertEqual(tp_fulfillment_status(tp_qty, net_received), "In Progress")
		self.assertEqual(pending_tp_quantity(tp_qty, net_received), 20.0)
		self.assertEqual(excess_tp_received_quantity(tp_qty, net_received), 0.0)

	def test_edge_case_5_multiple_grns_partial(self):
		"""TP = 300, GRNs: 100 + 100 + 88 = 288 -> In Progress."""
		tp_qty = 300.0
		grns = [
			{"net_weight": 100.0, "deduction": 2.0},
			{"net_weight": 100.0, "deduction": 2.0},
			{"net_weight": 88.0, "deduction": 2.0},
		]
		total_net = sum(grn_received_quantity(g) for g in grns)
		self.assertEqual(total_net, 288.0)
		self.assertEqual(tp_fulfillment_status(tp_qty, total_net), "In Progress")
		self.assertEqual(remaining_tp_quantity(tp_qty, total_net), 12.0)

	def test_edge_case_6_multiple_grns_complete(self):
		"""TP = 300, GRNs: 100 + 100 + 100 = 300 -> TP Completed."""
		tp_qty = 300.0
		grns = [
			{"net_weight": 100.0, "deduction": 2.0},
			{"net_weight": 100.0, "deduction": 2.0},
			{"net_weight": 100.0, "deduction": 2.0},
		]
		total_net = sum(grn_received_quantity(g) for g in grns)
		self.assertEqual(total_net, 300.0)
		self.assertEqual(tp_fulfillment_status(tp_qty, total_net), "TP Completed")
		self.assertEqual(remaining_tp_quantity(tp_qty, total_net), 0.0)

	def test_edge_case_7_deduction_not_used_as_tp_received(self):
		"""Verify that Chhatni deduction is NOT used as TP received quantity."""
		grn = {
			"load_weight": 150.0,
			"tare_weight": 100.0,
			"gross_weight": 50.0,
			"gunny_weight": 0.0,
			"deduction": 2.0,
			"net_weight": 48.0,
		}
		received = grn_received_quantity(grn)
		self.assertEqual(received, 48.0)
		self.assertNotEqual(received, 50.0)

	def test_edge_case_8_gunny_weight_not_independently_altered(self):
		"""Verify gunny weight is NOT independently added/subtracted by the TP fulfillment engine."""
		grn = {
			"gross_weight": 50.0,
			"gunny_weight": 1.5,
			"deduction": 2.0,
			"net_weight": 46.5,
		}
		received = grn_received_quantity(grn)
		self.assertEqual(received, 46.5)

	def test_chhatni_received_percentage_formula(self):
		"""Verify Received Chhatni % formula: max(0, ((Received - TP) / TP) * 100)."""
		# 1. Received below TP -> 0%
		self.assertEqual(received_chhatni_pct(288.0, 300.0), 0.0)
		status, _ = evaluate_chhatni_fulfillment(300.0, 288.0, 4.0, 12.0)
		self.assertEqual(status, CHHATNI_NOT_RECEIVED)

		# 2. Received equal to TP -> 0%
		self.assertEqual(received_chhatni_pct(300.0, 300.0), 0.0)
		status, _ = evaluate_chhatni_fulfillment(300.0, 300.0, 4.0, 12.0)
		self.assertEqual(status, CHHATNI_NOT_RECEIVED)

		# 3. Received above TP -> correct positive excess %
		self.assertEqual(received_chhatni_pct(312.0, 300.0), 4.0)
		status, _ = evaluate_chhatni_fulfillment(300.0, 312.0, 4.0, 12.0)
		self.assertEqual(status, CHHATNI_RECEIVED)

		# 4. Zero or missing TP quantity -> 0%
		self.assertEqual(received_chhatni_pct(300.0, 0.0), 0.0)
		self.assertEqual(received_chhatni_pct(300.0, -10.0), 0.0)

	def test_mandi_book_columns_order(self):
		"""Verify Mandi Book columns include Total Gross Wt, Total Gunny Wt, Total Deduction Received, Pending Qty, Excess Received Qty in required sequence."""
		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		# Ensure fields exist
		self.assertIn("tp_quantity", fieldnames)
		self.assertIn("total_gross_weight", fieldnames)
		self.assertIn("total_gunny_weight", fieldnames)
		self.assertIn("total_deduction_received", fieldnames)
		self.assertIn("total_received", fieldnames)
		self.assertIn("pending_qty", fieldnames)
		self.assertIn("excess_received_qty", fieldnames)
		self.assertIn("tp_status", fieldnames)

		# Ensure correct consecutive sequence: TP Qty -> Total Gross Wt -> Gunny Type -> Total Gunny Wt -> Total Deduction Received -> Total Qty Received -> Pending Qty -> Excess Received Qty -> TP Status
		idx_tp = fieldnames.index("tp_quantity")
		idx_gw = fieldnames.index("total_gross_weight")
		idx_gt = fieldnames.index("summary_gunny_type")
		idx_gunny = fieldnames.index("total_gunny_weight")
		idx_ded = fieldnames.index("total_deduction_received")
		idx_tot = fieldnames.index("total_received")
		idx_pen = fieldnames.index("pending_qty")
		idx_exc = fieldnames.index("excess_received_qty")
		idx_stat = fieldnames.index("tp_status")

		self.assertEqual(idx_gw, idx_tp + 1)
		self.assertEqual(idx_gt, idx_gw + 1)
		self.assertEqual(idx_gunny, idx_gt + 1)
		self.assertEqual(idx_ded, idx_gunny + 1)
		self.assertEqual(idx_tot, idx_ded + 1)
		self.assertEqual(idx_pen, idx_tot + 1)
		self.assertEqual(idx_exc, idx_pen + 1)
		self.assertEqual(idx_stat, idx_exc + 1)

	def test_real_database_case_mandi_book(self):
		"""Test the real 300 TP vs 288 Net case from site data in Mandi Book."""
		columns, data = execute_mandi_book({"transit_pass_no": "TP-300-6P"})
		self.assertTrue(len(data) > 0)
		row = data[0]
		self.assertEqual(row["tp_quantity"], 300.0)
		self.assertEqual(row["total_gross_weight"], 300.0)
		self.assertEqual(row["total_gunny_weight"], 0.0)
		self.assertEqual(row["total_deduction_received"], 12.0)
		self.assertEqual(row["total_received"], 288.0)
		self.assertEqual(row["pending_qty"], 12.0)
		self.assertEqual(row["excess_received_qty"], 0.0)
		self.assertEqual(row["tp_status"], "In Progress")
		self.assertEqual(row["actual_chhatni_pct"], 0.0)
		# Mandi Book status comes from saved Chhatni records; none exist for this pass yet.
		self.assertEqual(row["chhatni_status"], "Chhatni Pending")

	def test_adding_grn_to_reach_300_completes_tp(self):
		"""Verify that adding enough Net Weight to reach 300 QTL marks TP as Completed in GRN and Mandi Book."""
		from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass

		pass_key = "M051007-MALMANDA(S1051105)-K25-TP-300-6P"
		# Pre-condition: 288 received, In Progress, 12 pending, 0 excess
		_, data_before = execute_mandi_book({"transit_pass_no": "TP-300-6P"})
		row_before = data_before[0]
		self.assertEqual(row_before["total_received"], 288.0)
		self.assertEqual(row_before["pending_qty"], 12.0)
		self.assertEqual(row_before["excess_received_qty"], 0.0)
		self.assertEqual(row_before["tp_status"], "In Progress")

		# Create a temporary 7th GRN Note with 12.0 net weight
		test_grn = frappe.new_doc("GRN Note")
		test_grn.pass_unique_key = pass_key
		test_grn.is_local_procurement = 0
		test_grn.tp_quantity = 300.0
		test_grn.net_weight = 12.0
		test_grn.gross_vehicle_weight = 112.0
		test_grn.tare_weight = 100.0
		test_grn.gross_weight = 12.0
		test_grn.deduction = 0.0
		test_grn.chhatni = 4.0
		test_grn.receipt_date = "2026-10-08"
		test_grn.receipt_time = "15:00:00"
		test_grn.receipt_datetime = "2026-10-08 15:00:00"
		test_grn.flags.ignore_mandatory = True
		test_grn.flags.ignore_validate = True
		test_grn.insert(ignore_permissions=True)

		try:
			refresh_tp_fulfillment_for_pass(pass_key)

			# Verify GRN fulfillment fields
			updated_row = frappe.db.get_value(
				"GRN Note",
				test_grn.name,
				["received_quantity", "tp_cumulative_received", "tp_fulfillment_status"],
				as_dict=True,
			)
			self.assertEqual(flt(updated_row.received_quantity), 12.0)
			self.assertEqual(flt(updated_row.tp_cumulative_received), 300.0)
			self.assertEqual(updated_row.tp_fulfillment_status, "TP Completed")

			# Verify Mandi Book
			_, data_after = execute_mandi_book({"transit_pass_no": "TP-300-6P"})
			row_after = data_after[0]
			self.assertEqual(row_after["total_received"], 300.0)
			self.assertEqual(row_after["pending_qty"], 0.0)
			self.assertEqual(row_after["excess_received_qty"], 0.0)
			self.assertEqual(row_after["tp_status"], "TP Completed")
		finally:
			# Clean up test GRN
			frappe.delete_doc("GRN Note", test_grn.name, force=True, ignore_permissions=True)
			refresh_tp_fulfillment_for_pass(pass_key)

		# Verify restored to 288 / In Progress / Pending 12 / Excess 0
		_, data_restored = execute_mandi_book({"transit_pass_no": "TP-300-6P"})
		row_restored = data_restored[0]
		self.assertEqual(row_restored["total_received"], 288.0)
		self.assertEqual(row_restored["pending_qty"], 12.0)
		self.assertEqual(row_restored["excess_received_qty"], 0.0)
		self.assertEqual(row_restored["tp_status"], "In Progress")

	def test_mandi_book_detail_columns_present(self):
		"""Verify all detail columns for GRN and Entry are present in get_columns() and Detail Type is removed."""
		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		expected_detail_fields = [
			"grn_no",
			"rst_no",
			"vehicle_no",
			"load_weight",
			"tare_weight",
			"gross_weight",
			"gunny_type",
			"gunny_weight",
			"deduction",
			"net_weight",
			"entry",
			"agent_name",
			"entry_quantity",
			"entry_price_per_quintal",
			"total_amount",
		]
		for f in expected_detail_fields:
			self.assertIn(f, fieldnames, f"Expected detail field {f} in Mandi Book columns")

		# Verify removal of Detail Type, GRN Details and Entry Details columns
		self.assertNotIn("detail_type", fieldnames, "Detail Type column must be removed")
		self.assertNotIn("grn_count", fieldnames, "GRN Details column must be removed")
		self.assertNotIn("entry_count", fieldnames, "Entry Details column must be removed")
		labels = [c["label"] for c in columns]
		self.assertNotIn("Detail Type", labels)
		self.assertNotIn("GRN Details", labels)
		self.assertNotIn("Entry Details", labels)

	def test_mandi_book_tp138_multiple_grns_and_entry_grouped(self):
		"""Verify TP 138 with 3 GRNs and 1 Entry outputs 3 aligned rows with paired GRN and Entry."""
		_, data = execute_mandi_book({"transit_pass_no": "138"})
		# Filter for TP 138 specifically (in case '138' matches substring in other TPs)
		rows = [r for r in data if r.get("pass_unique_key") == "M051007-DUDUKA(S1050113)-K25-TP138" or r.get("tp_key") == "M051007-DUDUKA(S1050113)-K25-TP138"]
		if not rows:
			rows = data
		self.assertEqual(len(rows), 3, f"Expected exactly 3 rows (3 GRNs paired with 1 Entry), got {len(rows)}")

		# Row 0: TP summary + first GRN + first Entry paired together
		row0 = rows[0]
		self.assertEqual(row0["transit_pass_no"], "138")
		self.assertEqual(row0["tp_quantity"], 358.78)
		self.assertEqual(row0["total_gross_weight"], 377.925)
		self.assertEqual(row0["total_gunny_weight"], 3.0)
		self.assertEqual(row0["total_deduction_received"], 16.145)
		self.assertEqual(row0["total_received"], 358.78)
		self.assertEqual(row0["pending_qty"], 0.0)
		self.assertEqual(row0["tp_status"], "TP Completed")
		self.assertEqual(row0["detail_type"], "GRN & Entry")
		self.assertTrue(row0["grn_no"])
		self.assertTrue(row0["rst_no"])
		self.assertEqual(flt(row0["net_weight"]), 120.0)
		self.assertEqual(row0["entry"], "EN-2026-00002")
		self.assertEqual(row0["agent_name"], "Arjun")
		self.assertEqual(flt(row0["entry_quantity"]), 50.0)
		self.assertEqual(flt(row0["entry_price_per_quintal"]), 2300.0)
		self.assertEqual(flt(row0["total_amount"]), 115000.0)

		# Rows 1 and 2: Second and Third GRNs with BLANK TP cells and BLANK Entry cells
		for i in (1, 2):
			row_grn = rows[i]
			self.assertEqual(row_grn["transit_pass_no"], "")
			self.assertEqual(row_grn["season"], "")
			self.assertEqual(row_grn["ppc_name"], "")
			self.assertEqual(row_grn["mill_name"], "")
			self.assertIsNone(row_grn["tp_quantity"])
			self.assertIsNone(row_grn["total_gross_weight"])
			self.assertIsNone(row_grn["total_gunny_weight"])
			self.assertIsNone(row_grn["total_deduction_received"])
			self.assertIsNone(row_grn["total_received"])
			self.assertIsNone(row_grn["pending_qty"])
			self.assertEqual(row_grn["tp_status"], "")
			self.assertEqual(row_grn["detail_type"], "GRN")
			self.assertTrue(row_grn["grn_no"])
			self.assertTrue(row_grn["rst_no"])
			self.assertGreater(flt(row_grn["net_weight"]), 0)
			self.assertEqual(row_grn["entry"], "")
			self.assertEqual(row_grn["agent_name"], "")
			self.assertIsNone(row_grn["entry_quantity"])
			self.assertIsNone(row_grn["entry_price_per_quintal"])
			self.assertIsNone(row_grn["total_amount"])

		# Verify all 3 GRNs and 1 Entry are present without duplication or omission
		grn_nos = [r["grn_no"] for r in rows if r["grn_no"]]
		self.assertEqual(len(grn_nos), 3)
		self.assertEqual(len(set(grn_nos)), 3)
		entry_nos = [r["entry"] for r in rows if r["entry"]]
		self.assertEqual(entry_nos, ["EN-2026-00002"])

		# Verify total net weights of GRNs equal total received
		total_grn_net = sum(flt(r["net_weight"]) for r in rows if r["net_weight"])
		self.assertAlmostEqual(total_grn_net, 358.78, places=3)
		self.assertEqual(row0["total_received"], total_grn_net)

	def test_mandi_book_multi_grn_tp300(self):
		"""Verify TP-300-6P with 6 GRNs displays 6 rows with summary on first row and blanks on 5 rows."""
		_, data = execute_mandi_book({"transit_pass_no": "TP-300-6P"})
		self.assertEqual(len(data), 6, f"Expected 6 rows for TP-300-6P, got {len(data)}")

		# Row 0: TP summary
		self.assertEqual(data[0]["transit_pass_no"], "TP-300-6P")
		self.assertEqual(data[0]["tp_quantity"], 300.0)
		self.assertEqual(data[0]["total_gross_weight"], 300.0)
		self.assertEqual(data[0]["total_gunny_weight"], 0.0)
		self.assertEqual(data[0]["total_deduction_received"], 12.0)
		self.assertEqual(data[0]["total_received"], 288.0)
		self.assertEqual(data[0]["pending_qty"], 12.0)
		self.assertEqual(data[0]["tp_status"], "In Progress")
		self.assertEqual(data[0]["detail_type"], "GRN")
		self.assertEqual(data[0]["rst_no"], "RST-300-01")
		self.assertEqual(flt(data[0]["net_weight"]), 48.0)

		# Subsequent 5 rows: blank TP cells
		for i in range(1, 6):
			self.assertEqual(data[i]["transit_pass_no"], "")
			self.assertIsNone(data[i]["tp_quantity"])
			self.assertIsNone(data[i]["total_gross_weight"])
			self.assertIsNone(data[i]["total_gunny_weight"])
			self.assertIsNone(data[i]["total_deduction_received"])
			self.assertIsNone(data[i]["total_received"])
			self.assertEqual(data[i]["detail_type"], "GRN")
			self.assertEqual(data[i]["rst_no"], f"RST-300-0{i+1}")
			self.assertEqual(flt(data[i]["net_weight"]), 48.0)

		# Net total
		self.assertEqual(sum(flt(r["net_weight"]) for r in data), 288.0)

	def test_mandi_book_3_grns_2_entries_aligned(self):
		"""Test 3 GRNs and 2 Entries aligned row-by-row (max(3, 2) = 3 rows) without duplication or omission."""
		test_pass_key = "M051007-TESTMULTI-K25-TP-3G2E"
		season = "Kharif(2025)"

		grn1 = frappe.new_doc("GRN Note")
		grn1.pass_unique_key = test_pass_key
		grn1.transit_pass_no = "TP-3G2E"
		grn1.cmr_season = season
		grn1.ppc_name = "TEST PPC"
		grn1.mill_name = "Shree Shyamji"
		grn1.tp_quantity = 200.0
		grn1.net_weight = 60.0
		grn1.rst_no = "RST-M1"
		grn1.is_local_procurement = 0
		grn1.receipt_date = "2026-10-09"
		grn1.receipt_time = "10:00:00"
		grn1.receipt_datetime = "2026-10-09 10:00:00"
		grn1.flags.ignore_mandatory = True
		grn1.flags.ignore_validate = True
		grn1.insert(ignore_permissions=True)

		grn2 = frappe.new_doc("GRN Note")
		grn2.pass_unique_key = test_pass_key
		grn2.transit_pass_no = "TP-3G2E"
		grn2.cmr_season = season
		grn2.ppc_name = "TEST PPC"
		grn2.mill_name = "Shree Shyamji"
		grn2.tp_quantity = 200.0
		grn2.net_weight = 80.0
		grn2.rst_no = "RST-M2"
		grn2.is_local_procurement = 0
		grn2.receipt_date = "2026-10-09"
		grn2.receipt_time = "11:00:00"
		grn2.receipt_datetime = "2026-10-09 11:00:00"
		grn2.flags.ignore_mandatory = True
		grn2.flags.ignore_validate = True
		grn2.insert(ignore_permissions=True)

		grn3 = frappe.new_doc("GRN Note")
		grn3.pass_unique_key = test_pass_key
		grn3.transit_pass_no = "TP-3G2E"
		grn3.cmr_season = season
		grn3.ppc_name = "TEST PPC"
		grn3.mill_name = "Shree Shyamji"
		grn3.tp_quantity = 200.0
		grn3.net_weight = 30.0
		grn3.rst_no = "RST-M3"
		grn3.is_local_procurement = 0
		grn3.receipt_date = "2026-10-09"
		grn3.receipt_time = "12:00:00"
		grn3.receipt_datetime = "2026-10-09 12:00:00"
		grn3.flags.ignore_mandatory = True
		grn3.flags.ignore_validate = True
		grn3.insert(ignore_permissions=True)

		entry1 = frappe.new_doc("Entry")
		entry1.pass_unique_key = test_pass_key
		entry1.agent_name = "Agent Alpha"
		entry1.entry_quantity = 50.0
		entry1.entry_price_per_quintal = 2200.0
		entry1.total_amount = 110000.0
		entry1.flags.ignore_mandatory = True
		entry1.flags.ignore_validate = True
		entry1.insert(ignore_permissions=True)

		entry2 = frappe.new_doc("Entry")
		entry2.pass_unique_key = test_pass_key
		entry2.agent_name = "Agent Beta"
		entry2.entry_quantity = 40.0
		entry2.entry_price_per_quintal = 2250.0
		entry2.total_amount = 90000.0
		entry2.flags.ignore_mandatory = True
		entry2.flags.ignore_validate = True
		entry2.insert(ignore_permissions=True)

		try:
			_, data = execute_mandi_book({"transit_pass_no": "TP-3G2E"})
			# Exactly 3 rows: max(3 GRNs, 2 Entries) = 3 rows
			self.assertEqual(len(data), 3, f"Expected exactly 3 rows (3 GRNs paired with 2 Entries), got {len(data)}")

			# Row 0: TP summary + GRN 1 + Entry 1 paired
			self.assertEqual(data[0]["transit_pass_no"], "TP-3G2E")
			self.assertEqual(data[0]["tp_quantity"], 200.0)
			self.assertEqual(data[0]["total_received"], 170.0)
			self.assertEqual(data[0]["pending_qty"], 30.0)
			self.assertEqual(data[0]["detail_type"], "GRN & Entry")
			self.assertEqual(data[0]["rst_no"], "RST-M1")
			self.assertEqual(flt(data[0]["net_weight"]), 60.0)
			self.assertEqual(data[0]["entry"], entry1.name)
			self.assertEqual(data[0]["agent_name"], "Agent Alpha")
			self.assertEqual(flt(data[0]["entry_quantity"]), 50.0)

			# Row 1: Blank TP + GRN 2 + Entry 2 paired
			self.assertEqual(data[1]["transit_pass_no"], "")
			self.assertIsNone(data[1]["tp_quantity"])
			self.assertIsNone(data[1]["total_received"])
			self.assertEqual(data[1]["detail_type"], "GRN & Entry")
			self.assertEqual(data[1]["rst_no"], "RST-M2")
			self.assertEqual(flt(data[1]["net_weight"]), 80.0)
			self.assertEqual(data[1]["entry"], entry2.name)
			self.assertEqual(data[1]["agent_name"], "Agent Beta")
			self.assertEqual(flt(data[1]["entry_quantity"]), 40.0)

			# Row 2: Blank TP + GRN 3 + Blank Entry (unmatched cell left blank)
			self.assertEqual(data[2]["transit_pass_no"], "")
			self.assertIsNone(data[2]["tp_quantity"])
			self.assertEqual(data[2]["detail_type"], "GRN")
			self.assertEqual(data[2]["rst_no"], "RST-M3")
			self.assertEqual(flt(data[2]["net_weight"]), 30.0)
			self.assertEqual(data[2]["entry"], "")
			self.assertEqual(data[2]["agent_name"], "")
			self.assertIsNone(data[2]["entry_quantity"])
			self.assertIsNone(data[2]["entry_price_per_quintal"])
			self.assertIsNone(data[2]["total_amount"])

			# Ensure all records are present without omission or duplication
			grn_rst = [r["rst_no"] for r in data if r["rst_no"]]
			self.assertEqual(grn_rst, ["RST-M1", "RST-M2", "RST-M3"])
			entries = [r["entry"] for r in data if r["entry"]]
			self.assertEqual(entries, [entry1.name, entry2.name])
		finally:
			frappe.delete_doc("GRN Note", grn1.name, force=True, ignore_permissions=True)
			frappe.delete_doc("GRN Note", grn2.name, force=True, ignore_permissions=True)
			frappe.delete_doc("GRN Note", grn3.name, force=True, ignore_permissions=True)
			frappe.delete_doc("Entry", entry1.name, force=True, ignore_permissions=True)
			frappe.delete_doc("Entry", entry2.name, force=True, ignore_permissions=True)

	def test_mandi_book_1_grn_2_entries_aligned(self):
		"""Test 1 GRN and 2 Entries aligned row-by-row (max(1, 2) = 2 rows) without duplication or omission."""
		test_pass_key = "M051007-TESTMULTI-K25-TP-1G2E"
		season = "Kharif(2025)"

		grn1 = frappe.new_doc("GRN Note")
		grn1.pass_unique_key = test_pass_key
		grn1.transit_pass_no = "TP-1G2E"
		grn1.cmr_season = season
		grn1.ppc_name = "TEST PPC"
		grn1.mill_name = "Shree Shyamji"
		grn1.tp_quantity = 150.0
		grn1.net_weight = 100.0
		grn1.rst_no = "RST-S1"
		grn1.is_local_procurement = 0
		grn1.receipt_date = "2026-10-09"
		grn1.receipt_time = "10:00:00"
		grn1.receipt_datetime = "2026-10-09 10:00:00"
		grn1.flags.ignore_mandatory = True
		grn1.flags.ignore_validate = True
		grn1.insert(ignore_permissions=True)

		entry1 = frappe.new_doc("Entry")
		entry1.pass_unique_key = test_pass_key
		entry1.agent_name = "Agent Alpha"
		entry1.entry_quantity = 60.0
		entry1.entry_price_per_quintal = 2200.0
		entry1.total_amount = 132000.0
		entry1.flags.ignore_mandatory = True
		entry1.flags.ignore_validate = True
		entry1.insert(ignore_permissions=True)

		entry2 = frappe.new_doc("Entry")
		entry2.pass_unique_key = test_pass_key
		entry2.agent_name = "Agent Beta"
		entry2.entry_quantity = 40.0
		entry2.entry_price_per_quintal = 2250.0
		entry2.total_amount = 90000.0
		entry2.flags.ignore_mandatory = True
		entry2.flags.ignore_validate = True
		entry2.insert(ignore_permissions=True)

		try:
			_, data = execute_mandi_book({"transit_pass_no": "TP-1G2E"})
			# Exactly 2 rows: max(1 GRN, 2 Entries) = 2 rows
			self.assertEqual(len(data), 2, f"Expected exactly 2 rows (1 GRN paired with 2 Entries), got {len(data)}")

			# Row 0: TP summary + GRN 1 + Entry 1 paired
			self.assertEqual(data[0]["transit_pass_no"], "TP-1G2E")
			self.assertEqual(data[0]["tp_quantity"], 150.0)
			self.assertEqual(data[0]["total_received"], 100.0)
			self.assertEqual(data[0]["pending_qty"], 50.0)
			self.assertEqual(data[0]["detail_type"], "GRN & Entry")
			self.assertEqual(data[0]["rst_no"], "RST-S1")
			self.assertEqual(flt(data[0]["net_weight"]), 100.0)
			self.assertEqual(data[0]["entry"], entry1.name)
			self.assertEqual(data[0]["agent_name"], "Agent Alpha")
			self.assertEqual(flt(data[0]["entry_quantity"]), 60.0)

			# Row 1: Blank TP + Blank GRN + Entry 2 (unmatched GRN cells left blank)
			self.assertEqual(data[1]["transit_pass_no"], "")
			self.assertIsNone(data[1]["tp_quantity"])
			self.assertIsNone(data[1]["total_received"])
			self.assertEqual(data[1]["detail_type"], "Entry")
			self.assertEqual(data[1]["grn_no"], "")
			self.assertEqual(data[1]["rst_no"], "")
			self.assertIsNone(data[1]["net_weight"])
			self.assertEqual(data[1]["entry"], entry2.name)
			self.assertEqual(data[1]["agent_name"], "Agent Beta")
			self.assertEqual(flt(data[1]["entry_quantity"]), 40.0)

			# Ensure all records are present without omission or duplication
			grn_rst = [r["rst_no"] for r in data if r["rst_no"]]
			self.assertEqual(grn_rst, ["RST-S1"])
			entries = [r["entry"] for r in data if r["entry"]]
			self.assertEqual(entries, [entry1.name, entry2.name])
		finally:
			frappe.delete_doc("GRN Note", grn1.name, force=True, ignore_permissions=True)
			frappe.delete_doc("Entry", entry1.name, force=True, ignore_permissions=True)
			frappe.delete_doc("Entry", entry2.name, force=True, ignore_permissions=True)

	def test_mandi_book_visual_grouping_serial_and_borders(self):
		"""Verify that Mandi Book UI grouping assigns exactly one serial number per TP group,
		blanks subsequent detail rows belonging to the same TP, and identifies clear group boundaries and vertical separators."""
		import json
		import subprocess

		# 1. Fetch real report data for TP 138 (3 rows: 3 GRNs paired with 1 Entry)
		_, tp138_data = execute_mandi_book({"transit_pass_no": "138"})
		self.assertEqual(len(tp138_data), 3, f"Expected 3 rows for TP 138, got {len(tp138_data)}")

		# 2. Fetch real report data for TP-300-6P (6 rows: 6 GRNs)
		_, tp300_data = execute_mandi_book({"transit_pass_no": "TP-300-6P"})
		self.assertEqual(len(tp300_data), 6, f"Expected 6 rows for TP-300-6P, got {len(tp300_data)}")

		# Combine both TPs into a 9-row dataset to test consecutive TP groups
		combined_data = list(tp138_data) + list(tp300_data)
		self.assertEqual(len(combined_data), 9)

		js_path = frappe.get_app_path("ivri_od", "procurement", "report", "mandi_book", "mandi_book.js")

		# Execute the grouping algorithm defined in mandi_book.js via Node
		node_script = """
		const fs = require('fs');
		const code = fs.readFileSync(__JS_PATH__, 'utf8');
""".replace("__JS_PATH__", json.dumps(js_path)) + """

		global.frappe = {
			query_reports: {},
			utils: { escape_html: (s) => s, get_form_link: () => '#' }
		};
		global.__ = (s) => s;
		global.flt = (v) => parseFloat(v) || 0;
		global.document = {
			head: { appendChild: () => {} },
			getElementById: () => null,
			createElement: () => ({ id: '', textContent: '' })
		};

		eval(code);

		const report = frappe.query_reports['Mandi Book'];
		const inputData = JSON.parse(fs.readFileSync(0, 'utf8'));

		const mockColumns = [
			{ id: '_rowIndex', content: 'Sr', format: null },
			{ id: 'transit_pass_no', content: 'TP No' },
			{ id: 'entry', content: 'Entry' },
			{ id: 'grn_no', content: 'GRN No.' }
		];

		const mockRows = inputData.map((d, i) => {
			const r = [
				{ content: String(i + 1), html: String(i + 1), rowIndex: i, colIndex: 0 },
				{ content: d.transit_pass_no, rowIndex: i, colIndex: 1 },
				{ content: d.entry || '', rowIndex: i, colIndex: 2 },
				{ content: d.grn_no || '', rowIndex: i, colIndex: 3 }
			];
			r.meta = { rowIndex: i };
			return r;
		});

		let createdStyle = null;
		global.document.createElement = () => {
			createdStyle = { id: '', textContent: '' };
			return createdStyle;
		};

		const mockDataTable = {
			datamanager: {
				data: inputData,
				rows: mockRows,
				rowViewOrder: inputData.map((_, i) => i),
				getColumnIndexById: (id) => mockColumns.findIndex(c => c.id === id),
				getColumnById: (id) => mockColumns.find(c => c.id === id),
				getData: (i) => inputData[i],
				getRow: (i) => mockRows[i]
			},
			renderBody: () => {}
		};

		report.after_datatable_render(mockDataTable);

		const srCol = mockDataTable.datamanager.getColumnById('_rowIndex');
		const result = {
			row_serials: mockRows.map((r, i) => ({
				rowIndex: i,
				content: r[0].content,
				html: r[0].html,
				format: srCol.format(r[0].content, r, srCol, inputData[i])
			})),
			style_css: createdStyle ? createdStyle.textContent : ''
		};

		process.stdout.write(JSON.stringify(result));
		"""

		proc = subprocess.run(
			["node", "-e", node_script],
			input=json.dumps(combined_data, default=str),
			capture_output=True,
			text=True,
			cwd=frappe.get_app_path("frappe", "../.."),
		)
		if proc.returncode != 0:
			raise AssertionError(f"Node script failed (exit {proc.returncode}):\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")
		result = json.loads(proc.stdout)
		row_serials = result["row_serials"]

		# Verify TP 138 (rows 0..2):
		# Row 0: Serial number is "1"
		self.assertEqual(row_serials[0]["content"], "1")
		self.assertEqual(row_serials[0]["html"], "1")
		self.assertEqual(row_serials[0]["format"], "1")

		# Rows 1..2: Blank serial numbers
		for idx in [1, 2]:
			self.assertEqual(row_serials[idx]["content"], "", f"Row {idx} serial number must be blank")
			self.assertEqual(row_serials[idx]["html"], "", f"Row {idx} html must be blank")
			self.assertEqual(row_serials[idx]["format"], "", f"Row {idx} format must be blank")

		# Verify TP-300-6P (rows 3..8):
		# Row 3: Serial number is "2"
		self.assertEqual(row_serials[3]["content"], "2")
		self.assertEqual(row_serials[3]["html"], "2")
		self.assertEqual(row_serials[3]["format"], "2")

		# Rows 4..8: Blank serial numbers
		for idx in [4, 5, 6, 7, 8]:
			self.assertEqual(row_serials[idx]["content"], "", f"Row {idx} serial number must be blank")
			self.assertEqual(row_serials[idx]["html"], "", f"Row {idx} html must be blank")
			self.assertEqual(row_serials[idx]["format"], "", f"Row {idx} format must be blank")

		# Exactly 2 displayed serial numbers across the 9 rows:
		non_empty_serials = [r["content"] for r in row_serials if r["content"]]
		self.assertEqual(non_empty_serials, ["1", "2"])

		# Verify group boundary horizontal separators:
		style_css = result["style_css"]
		self.assertIn(".dt-row-2 .dt-cell", style_css, "Last row of TP 138 (index 2) must have separator border")
		self.assertIn(".dt-row-8 .dt-cell", style_css, "Last row of TP-300-6P (index 8) must have separator border")
		self.assertIn("border-bottom: 2px solid", style_css)

		# Verify vertical section separators:
		self.assertIn(".dt-cell--col-2", style_css, "Entry column must have vertical border")
		self.assertIn(".dt-cell--col-3", style_css, "GRN No column must have vertical border")
		self.assertIn("border-left: 2px solid", style_css)


def run():
	suite = unittest.TestLoader().loadTestsFromTestCase(TestTPFulfillment)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	if not result.wasSuccessful():
		for test, err in result.errors:
			print(f"\nERROR in {test}:\n{err}")
		for test, fail in result.failures:
			print(f"\nFAILURE in {test}:\n{fail}")
		raise RuntimeError(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
	print(f"All {result.testsRun} tests passed successfully!")
	return True
