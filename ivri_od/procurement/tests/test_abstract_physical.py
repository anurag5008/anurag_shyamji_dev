# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from ivri_od.procurement.report.abstract_physical.abstract_physical import (
	execute,
	get_columns,
	get_data,
)


class TestAbstractPhysical(FrappeTestCase):
	def test_columns_structure_and_labels(self):
		"""Columns must have Season, PPC (Link to PPC Master), and the physical procurement metrics."""
		columns = get_columns()
		self.assertEqual(len(columns), 7, "Report must have 7 columns (including Season)")

		labels = [c["label"] for c in columns]
		fieldnames = [c["fieldname"] for c in columns]

		self.assertEqual(labels[0], "Season")
		self.assertEqual(labels[1], "PPC")
		self.assertNotEqual(labels[1], "PACS Name", "PPC column must NOT be PACS Name")
		self.assertEqual(labels[2], "TP Quantity (QTL)")
		self.assertEqual(labels[3], "Physical Paddy (QTL)")
		self.assertEqual(labels[4], "Entry Qty (QTL)")
		self.assertEqual(labels[5], "Chhatni Quantity (QTL)")
		self.assertEqual(labels[6], "Chhatni %")

		self.assertEqual(fieldnames, [
			"season",
			"ppc",
			"tp_quantity",
			"physical_paddy",
			"entry_qty",
			"chhatni_quantity",
			"chhatni_pct",
		])

		self.assertEqual(columns[0]["fieldtype"], "Link")
		self.assertEqual(columns[0]["options"], "Season Master")
		self.assertEqual(columns[1]["fieldtype"], "Link")
		self.assertEqual(columns[1]["options"], "PPC Master")
		self.assertEqual(columns[2]["fieldtype"], "Float")
		self.assertEqual(columns[3]["fieldtype"], "Float")
		self.assertEqual(columns[4]["fieldtype"], "Float")
		self.assertEqual(columns[5]["fieldtype"], "Float")
		self.assertEqual(columns[6]["fieldtype"], "Percent")

	def test_chhatni_percentage_formula_and_zero_division(self):
		"""Verify formula: Chhatni % = (Chhatni Quantity / (TP Quantity - Entry Qty)) * 100."""
		tp_qty = 500.0
		entry_qty = 30.0
		chhatni_qty = 18.8
		denom = tp_qty - entry_qty
		pct = flt((chhatni_qty / denom) * 100.0, 2)
		self.assertEqual(pct, 4.00)

		# Zero denominator safe handling: TP = 50, Entry = 50
		tp_zero = 50.0
		entry_zero = 50.0
		denom_zero = tp_zero - entry_zero
		pct_zero = flt((chhatni_qty / denom_zero) * 100.0, 2) if denom_zero > 0 else 0.0
		self.assertEqual(pct_zero, 0.0)

		# Zero TP safe handling: TP = 0, Entry = 0
		denom_no_tp = 0.0 - 0.0
		pct_no_tp = flt((chhatni_qty / denom_no_tp) * 100.0, 2) if denom_no_tp > 0 else 0.0
		self.assertEqual(pct_no_tp, 0.0)

	def test_aggregation_duduka(self):
		"""DUDUKA on Kharif 2025: Physical = 666.176, Entry = 200.0, Chhatni = 23.659."""
		columns, data = execute({"ppc_name": "S1050113", "season": "Kharif 2025"})
		self.assertEqual(len(data), 1)
		row = data[0]

		self.assertEqual(row["season"], "Kharif 2025")
		self.assertEqual(row["ppc"], "DUDUKA(S1050113)")
		self.assertAlmostEqual(row["physical_paddy"], 666.176, places=3)
		self.assertAlmostEqual(row["entry_qty"], 200.0, places=3)
		self.assertAlmostEqual(row["chhatni_quantity"], 23.659, places=3)
		self.assertGreater(row["tp_quantity"], 3000.0)

		expected_pct = flt((row["chhatni_quantity"] / (row["tp_quantity"] - row["entry_qty"])) * 100.0, 2)
		self.assertEqual(row["chhatni_pct"], expected_pct)

	def test_aggregation_dholmandal(self):
		"""DHOLMANDAL on Kharif 2025: Physical = 1738.55, Chhatni = 74.25."""
		columns, data = execute({"ppc_name": "S1051411", "season": "Kharif 2025"})
		self.assertEqual(len(data), 1)
		row = data[0]

		self.assertEqual(row["ppc"], "DHOLMANDAL(S1051411)")
		self.assertAlmostEqual(row["physical_paddy"], 1738.55, places=2)
		self.assertAlmostEqual(row["chhatni_quantity"], 74.25, places=2)
		self.assertAlmostEqual(row["entry_qty"], 0.0, places=3)
		self.assertAlmostEqual(row["tp_quantity"], 4699.19, places=2)
		self.assertEqual(row["chhatni_pct"], 1.58)

	def test_season_separation(self):
		"""Kharif and Rabi seasons return their respective allocated PPCs."""
		_, data = execute({})
		# Total 49 rows: 48 Kharif + 1 Rabi
		self.assertEqual(len(data), 49)
		kharif_rows = [r for r in data if r["season"] == "Kharif 2025"]
		rabi_rows = [r for r in data if r["season"] == "Rabi 2025"]
		self.assertEqual(len(kharif_rows), 48)
		self.assertEqual(len(rabi_rows), 1)
		self.assertEqual(rabi_rows[0]["ppc_name"], "S1050215")

	def test_filters(self):
		"""Test season and ppc filters."""
		# Filter Kharif
		_, kharif_data = execute({"season": "Kharif 2025"})
		self.assertEqual(len(kharif_data), 48)
		for r in kharif_data:
			self.assertEqual(r["season"], "Kharif 2025")

		# Filter Rabi
		_, rabi_data = execute({"season": "Rabi 2025"})
		self.assertEqual(len(rabi_data), 1)
		for r in rabi_data:
			self.assertEqual(r["season"], "Rabi 2025")
			self.assertEqual(r["ppc_name"], "S1050215")

		# Filter by display name with season
		_, duduka_display_data = execute({"ppc_name": "DUDUKA(S1050113)", "season": "Kharif 2025"})
		self.assertEqual(len(duduka_display_data), 1)
		self.assertEqual(duduka_display_data[0]["ppc"], "DUDUKA(S1050113)")

		# Filter by display name without season -> only seasons where PPC has Target Allocation > 0
		_, duduka_all_seasons = execute({"ppc_name": "DUDUKA(S1050113)"})
		self.assertEqual(len(duduka_all_seasons), 1)
		self.assertEqual(duduka_all_seasons[0]["season"], "Kharif 2025")
		self.assertEqual(duduka_all_seasons[0]["ppc"], "DUDUKA(S1050113)")

	def test_ppc_without_target_allocation_does_not_appear(self):
		"""PPC present in PPC Master but with NO Target Allocation does NOT appear."""
		_, data = execute({"ppc_name": "S1050301", "season": "Rabi 2025"})
		self.assertEqual(len(data), 0, "PPC without Target Allocation must NOT appear")

	def test_valid_ppc_with_target_and_zero_transactions_shows_zeros(self):
		"""A PPC with Target Allocation > 0 and 0 transactions appears with 0 transaction quantities."""
		temp_code = "TEMP9911"
		temp_ppc = frappe.new_doc("PPC Master")
		temp_ppc.code = temp_code
		temp_ppc.ppc_name = "TEST_PHYSICAL_NO_TXN"
		temp_ppc.district = "Sundargarh"
		temp_ppc.is_active = 1
		temp_ppc.insert(ignore_permissions=True)

		temp_ta = frappe.new_doc("Target Allocation")
		temp_ta.season = "Kharif 2025"
		temp_ta.ppc_name = temp_code
		temp_ta.mill_name = "M051007"
		temp_ta.agent_name = "Direct"
		temp_ta.target_quantity = 500.0
		temp_ta.insert(ignore_permissions=True)

		try:
			_, data = execute({"ppc_name": temp_code, "season": "Kharif 2025"})
			self.assertEqual(len(data), 1)
			row = data[0]
			self.assertEqual(row["ppc_name"], temp_code)
			self.assertEqual(row["tp_quantity"], 0.0)
			self.assertEqual(row["physical_paddy"], 0.0)
			self.assertEqual(row["entry_qty"], 0.0)
			self.assertEqual(row["chhatni_quantity"], 0.0)
			self.assertEqual(row["chhatni_pct"], 0.0)
		finally:
			frappe.delete_doc("Target Allocation", temp_ta.name, force=True, ignore_permissions=True)
			frappe.delete_doc("PPC Master", temp_ppc.name, force=True, ignore_permissions=True)

	def test_transaction_with_obsolete_ppc_not_in_report(self):
		"""A transaction referencing an obsolete PPC name NOT in PPC Master does NOT appear."""
		_, data = execute({"season": "Rabi 2025"})
		all_ppcs = [r["ppc"] for r in data]
		all_ppc_names = [r["ppc_name"] for r in data]

		for raw in ("MY200714", "DHAMNAHANDI", "CHANDILI", "MY200704"):
			self.assertNotIn(raw, all_ppc_names)
			self.assertFalse(any(raw in p for p in all_ppcs), f"Obsolete PPC {raw} should not appear in report")

	def test_target_allocation_dynamic_change_and_lifecycle(self):
		"""
		Validate dynamic runtime loading and lifecycle in Abstract Physical:
		1. New PPC without target -> does NOT appear.
		2. Assign target 300 -> appears immediately.
		3. Set target to 0 -> does NOT appear.
		4. Delete Target Allocation -> does NOT appear.
		"""
		test_code = "TEMP9921"
		temp_doc = frappe.new_doc("PPC Master")
		temp_doc.code = test_code
		temp_doc.ppc_name = "AUTOTEST_PHYSICAL_DYNAMIC_PPC"
		temp_doc.district = "Sundargarh"
		temp_doc.is_active = 1
		temp_doc.insert(ignore_permissions=True)

		ta_doc = None
		try:
			# 1. Without Target Allocation -> does NOT appear
			_, d1 = execute({"ppc_name": test_code, "season": "Kharif 2025"})
			self.assertEqual(len(d1), 0, "PPC without Target Allocation must not appear")

			# 2. Create Target Allocation with 300 -> appears immediately
			ta_doc = frappe.new_doc("Target Allocation")
			ta_doc.season = "Kharif 2025"
			ta_doc.ppc_name = test_code
			ta_doc.mill_name = "M051007"
			ta_doc.agent_name = "Direct"
			ta_doc.target_quantity = 300.0
			ta_doc.insert(ignore_permissions=True)

			_, d2 = execute({"ppc_name": test_code, "season": "Kharif 2025"})
			self.assertEqual(len(d2), 1)
			self.assertEqual(d2[0]["ppc_name"], test_code)
			self.assertEqual(d2[0]["tp_quantity"], 0.0)

			# 3. Set target_quantity to 0 -> does NOT appear
			ta_doc.target_quantity = 0.0
			ta_doc.save(ignore_permissions=True)

			_, d3 = execute({"ppc_name": test_code, "season": "Kharif 2025"})
			self.assertEqual(len(d3), 0, "PPC with Target Quantity = 0 must not appear")

		finally:
			if ta_doc and frappe.db.exists("Target Allocation", ta_doc.name):
				frappe.delete_doc("Target Allocation", ta_doc.name, force=True, ignore_permissions=True)
			if frappe.db.exists("PPC Master", temp_doc.name):
				frappe.delete_doc("PPC Master", temp_doc.name, force=True, ignore_permissions=True)

		# 4. After deletion -> does NOT appear
		_, d4 = execute({"ppc_name": test_code, "season": "Kharif 2025"})
		self.assertEqual(len(d4), 0, "Deleted PPC must not appear in report")


def run():
	suite = unittest.TestLoader().loadTestsFromTestCase(TestAbstractPhysical)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	if not result.wasSuccessful():
		raise RuntimeError(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
	print(f"All {result.testsRun} tests passed successfully!")
	return True
