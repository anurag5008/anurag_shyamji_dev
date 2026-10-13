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
)
from ivri_od.procurement.report.mandi_book.mandi_book import execute as execute_mandi_book, get_columns


class TestTPFulfillment(FrappeTestCase):
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

	def test_chhatni_independence_from_tp_fulfillment(self):
		"""TP = 300, Net = 288 (In Progress), Deduction = 12 (4%), Assigned = 4% -> Chhatni Received."""
		tp_qty = 300.0
		net_received = 288.0
		deduction = 12.0
		assigned_chhatni = 4.0

		tp_status = tp_fulfillment_status(tp_qty, net_received)
		self.assertEqual(tp_status, "In Progress")

		chhatni_status, remark = evaluate_chhatni_fulfillment(
			tp_qty,
			net_received,
			assigned_chhatni,
			deduction,
		)
		self.assertEqual(chhatni_status, CHHATNI_RECEIVED)

	def test_mandi_book_columns_order(self):
		"""Verify Mandi Book columns include Pending Qty, Excess Received Qty in required sequence."""
		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]
		# Ensure fields exist
		self.assertIn("tp_quantity", fieldnames)
		self.assertIn("total_received", fieldnames)
		self.assertIn("pending_qty", fieldnames)
		self.assertIn("excess_received_qty", fieldnames)
		self.assertIn("tp_status", fieldnames)

		# Ensure correct consecutive sequence: TP Qty -> Total Qty Received -> Pending Qty -> Excess Received Qty -> TP Status
		idx_tp = fieldnames.index("tp_quantity")
		idx_tot = fieldnames.index("total_received")
		idx_pen = fieldnames.index("pending_qty")
		idx_exc = fieldnames.index("excess_received_qty")
		idx_stat = fieldnames.index("tp_status")

		self.assertEqual(idx_tot, idx_tp + 1)
		self.assertEqual(idx_pen, idx_tot + 1)
		self.assertEqual(idx_exc, idx_pen + 1)
		self.assertEqual(idx_stat, idx_exc + 1)

	def test_real_database_case_mandi_book(self):
		"""Test the real 300 TP vs 288 Net case from site data in Mandi Book."""
		columns, data = execute_mandi_book({"transit_pass_no": "TP-300-6P"})
		self.assertTrue(len(data) > 0)
		row = data[0]
		self.assertEqual(row["tp_quantity"], 300.0)
		self.assertEqual(row["total_received"], 288.0)
		self.assertEqual(row["pending_qty"], 12.0)
		self.assertEqual(row["excess_received_qty"], 0.0)
		self.assertEqual(row["tp_status"], "In Progress")
		self.assertEqual(row["chhatni_status"], "Chhatni Received")

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


def run():
	suite = unittest.TestLoader().loadTestsFromTestCase(TestTPFulfillment)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	if not result.wasSuccessful():
		raise RuntimeError(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
	print(f"All {result.testsRun} tests passed successfully!")
	return True
