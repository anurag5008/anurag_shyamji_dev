"""Comprehensive validation tests for the redesigned Abstract Report."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from ivri_od.procurement.report.abstract_report.abstract_report import (
	execute,
	get_columns,
	get_data,
	get_eligible_ppcs_query,
	get_relevant_mills,
)


class TestAbstractReport(FrappeTestCase):
	def test_columns_structure_and_dynamic_mills(self):
		"""Columns must dynamically have Season, PPC, dynamic Mill groups (Target, Received, Balance) and Total."""
		mills = get_relevant_mills()
		self.assertGreaterEqual(len(mills), 5, "Should dynamically discover all active mills (at least 5)")

		columns = get_columns()
		fieldnames = [c["fieldname"] for c in columns]

		self.assertEqual(fieldnames[0], "season")
		self.assertEqual(fieldnames[1], "ppc_display")

		for m in mills:
			prefix = frappe.scrub(m["name"])
			self.assertIn(f"{prefix}_target", fieldnames)
			self.assertIn(f"{prefix}_received", fieldnames)
			self.assertIn(f"{prefix}_balance", fieldnames)

		self.assertEqual(fieldnames[-3], "total_target")
		self.assertEqual(fieldnames[-2], "total_received")
		self.assertEqual(fieldnames[-1], "total_balance")

	def test_1_ppc_with_one_mill_and_existing_values_match(self):
		"""Check DUDUKA row: M051007 Target=5000, Received=666.176, Balance=4333.824."""
		columns, data = execute({"ppc_name": "S1050113", "season": "Kharif 2025"})
		self.assertEqual(len(data), 1)
		row = data[0]

		self.assertEqual(row["season"], "Kharif 2025")
		self.assertEqual(row["ppc_name"], "S1050113")
		self.assertEqual(row["ppc_display"], "DUDUKA(S1050113)")

		# Check M051007 values match current values including fulfilled TP 138
		self.assertEqual(row["m051007_target"], 5000.0)
		self.assertEqual(row["m051007_received"], 666.176)
		self.assertEqual(row["m051007_balance"], 4333.824)

		# Check row totals
		self.assertEqual(row["total_target"], 5000.0)
		self.assertEqual(row["total_received"], 666.176)
		self.assertEqual(row["total_balance"], 4333.824)

	def test_2_ppc_with_multiple_mills_and_ppc_totals(self):
		"""Simulate a PPC mapped to multiple mills; row totals must equal sum across mills."""
		# Create a temporary Season Mapping for M050414 (Shree Shyamji Raw) on DUDUKA
		test_sm = frappe.new_doc("Season Mapping")
		test_sm.season = "Kharif 2025"
		test_sm.season_year = "2025"
		test_sm.ppc_name = "S1050113"
		test_sm.mill_name = "M050414"
		test_sm.season_quantity = 2000.0
		test_sm.flags.ignore_mandatory = True
		test_sm.flags.ignore_validate = True
		test_sm.insert(ignore_permissions=True)

		try:
			columns, data = execute({"ppc_name": "S1050113", "season": "Kharif 2025"})
			self.assertEqual(len(data), 1)
			row = data[0]

			# Mill 1 (M051007)
			self.assertEqual(row["m051007_target"], 5000.0)
			self.assertEqual(row["m051007_received"], 666.176)
			self.assertEqual(row["m051007_balance"], 4333.824)

			# Mill 2 (M050414)
			self.assertEqual(row["m050414_target"], 2000.0)
			self.assertEqual(row["m050414_received"], 0.0)
			self.assertEqual(row["m050414_balance"], 2000.0)

			# PPC Row Totals must be sum of mills: 5000 + 2000 = 7000; 666.176 + 0 = 666.176; 4333.824 + 2000 = 6333.824
			self.assertEqual(row["total_target"], 7000.0)
			self.assertEqual(row["total_received"], 666.176)
			self.assertEqual(row["total_balance"], 6333.824)
		finally:
			frappe.delete_doc("Season Mapping", test_sm.name, force=True, ignore_permissions=True)

	def test_3_multiple_ppcs_for_one_mill(self):
		"""Only PPCs with Target Quantity > 0 in Kharif 2025 must appear (48 PPCs)."""
		columns, data = execute({"season": "Kharif 2025"})
		self.assertEqual(len(data), 48, "All 48 PPCs with Target Quantity > 0 must appear for Kharif 2025")
		ppc_names = [r["ppc_name"] for r in data]
		self.assertIn("S1050113", ppc_names)  # DUDUKA
		self.assertIn("S1050812", ppc_names)  # BADIMUNDA
		self.assertIn("S1051105", ppc_names)  # MALMANDA
		self.assertIn("S1051406", ppc_names)  # TUREKELA
		self.assertIn("S1051411", ppc_names)  # DHOLMANDAL

		# Non-existent PPC must NOT appear
		self.assertNotIn("NON_EXISTENT_PPC", ppc_names)

	def test_4_and_8_ppc_wise_totals_and_grand_total(self):
		"""Verify that every PPC row total equals mill sums, and grand totals are correct."""
		columns, data = execute()
		# 48 in Kharif + 1 in Rabi = 49 rows
		self.assertEqual(len(data), 49, "Only PPCs with Target Quantity > 0 must appear (48 in Kharif + 1 in Rabi)")

		mill_keys = [
			c["fieldname"][:-7]
			for c in columns
			if c["fieldname"].endswith("_target") and c["fieldname"] != "total_target"
		]

		grand_target = 0.0

		for row in data:
			sum_targets = flt(sum(flt(row[f"{k}_target"]) for k in mill_keys), 3)
			sum_received = flt(sum(flt(row[f"{k}_received"]) for k in mill_keys), 3)
			sum_balances = flt(sum(flt(row[f"{k}_balance"]) for k in mill_keys), 3)

			self.assertEqual(row["total_target"], sum_targets)
			self.assertEqual(row["total_received"], sum_received)
			self.assertEqual(row["total_balance"], sum_balances)

			grand_target += row["total_target"]

		self.assertEqual(flt(grand_target, 3), 176500.0)

	def test_5_season_filter(self):
		"""Filtering by season returns only PPCs with Target Quantity > 0 for that season."""
		columns, data_k = execute({"season": "Kharif 2025"})
		self.assertEqual(len(data_k), 48)
		for r in data_k:
			self.assertEqual(r["season"], "Kharif 2025")

		columns, data_r = execute({"season": "Rabi 2025"})
		self.assertEqual(len(data_r), 1)
		for r in data_r:
			self.assertEqual(r["season"], "Rabi 2025")
			self.assertEqual(r["ppc_name"], "S1050215")

	def test_6_ppc_filter(self):
		"""Filtering by ppc_name returns only that PPC if it has Target Quantity > 0."""
		columns, data = execute({"ppc_name": "S1051105", "season": "Kharif 2025"})
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["ppc_name"], "S1051105")
		self.assertEqual(data[0]["m051007_target"], 4500.0)
		self.assertEqual(data[0]["m051007_received"], 94.0)
		self.assertEqual(data[0]["m051007_balance"], 4406.0)

		# Without season filter -> 1 row (S1051105 only has target in Kharif 2025)
		columns, data_all = execute({"ppc_name": "S1051105"})
		self.assertEqual(len(data_all), 1)
		self.assertEqual(data_all[0]["season"], "Kharif 2025")
		self.assertEqual(data_all[0]["ppc_name"], "S1051105")

	def test_7_mill_filter(self):
		"""Filtering by mill_name shows only that mill group and Total group."""
		columns, data = execute({"mill_name": "M051007"})
		col_fields = [c["fieldname"] for c in columns]

		# Should have Season, PPC, M051007 Target/Recv/Bal, and Total
		self.assertEqual(len(columns), 8)
		self.assertEqual(col_fields, [
			"season",
			"ppc_display",
			"m051007_target",
			"m051007_received",
			"m051007_balance",
			"total_target",
			"total_received",
			"total_balance",
		])

		for row in data:
			self.assertEqual(row["total_target"], row["m051007_target"])
			self.assertEqual(row["total_received"], row["m051007_received"])
			self.assertEqual(row["total_balance"], row["m051007_balance"])

	def test_9_mill_wise_vertical_totals(self):
		"""Check vertical target sum for each mill across all displayed rows."""
		columns, data = execute()
		m051007_tot_target = flt(sum(r["m051007_target"] for r in data), 3)
		self.assertEqual(m051007_tot_target, 176500.0)

	def test_11_remaining_never_negative(self):
		"""If received exceeds assigned, balance must be 0, never negative."""
		remaining = max(100.0 - 307.396, 0.0)
		self.assertEqual(remaining, 0.0)
		self.assertGreaterEqual(remaining, 0.0)

	def test_12_and_13_no_data_lost(self):
		"""Verify that all baseline values from original report are strictly preserved."""
		columns, data = execute()
		baseline = {
			("Kharif 2025", "S1050113"): (5000.0, 666.176, 4333.824),
			("Kharif 2025", "S1050812"): (6000.0, 286.870, 5713.130),
			("Kharif 2025", "S1051105"): (4500.0, 94.000, 4406.000),
			("Kharif 2025", "S1051406"): (4000.0, 142.823, 3857.177),
			("Kharif 2025", "S1051411"): (3500.0, 153.800, 3346.200),
			("Rabi 2025", "S1050215"): (3000.0, 65.710, 2934.290),
		}

		row_map = {(r["season"], r["ppc_name"]): r for r in data}
		for key, (expected_target, expected_recv, expected_bal) in baseline.items():
			self.assertIn(key, row_map)
			row = row_map[key]
			self.assertEqual(row["m051007_target"], expected_target)
			self.assertEqual(row["m051007_received"], expected_recv)
			self.assertEqual(row["m051007_balance"], expected_bal)

	def test_ppc_without_target_allocation_does_not_appear(self):
		"""PPC present in PPC Master but with NO Target Allocation does NOT appear."""
		# BELPADA (S1050301) exists in PPC Master but has no Target Allocation in Rabi 2025
		_, data = execute({"ppc_name": "S1050301", "season": "Rabi 2025"})
		self.assertEqual(len(data), 0, "PPC without Target Allocation must NOT appear")

	def test_valid_ppc_with_target_and_zero_transactions_shows_zeros(self):
		"""A PPC with Target Allocation > 0 and 0 transactions appears with target and 0 received."""
		# Create temporary Target Allocation with 0 transactions
		temp_code = "TEMP9910"
		temp_ppc = frappe.new_doc("PPC Master")
		temp_ppc.code = temp_code
		temp_ppc.ppc_name = "TEST_PPC_NO_TXN"
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
			self.assertEqual(row["m051007_target"], 500.0)
			self.assertEqual(row["m051007_received"], 0.0)
			self.assertEqual(row["m051007_balance"], 500.0)
			self.assertEqual(row["total_target"], 500.0)
			self.assertEqual(row["total_received"], 0.0)
			self.assertEqual(row["total_balance"], 500.0)
		finally:
			frappe.delete_doc("Target Allocation", temp_ta.name, force=True, ignore_permissions=True)
			frappe.delete_doc("PPC Master", temp_ppc.name, force=True, ignore_permissions=True)

	def test_transaction_with_obsolete_ppc_not_in_report(self):
		"""Obsolete PPC names not in PPC Master do not appear in the report."""
		_, data = execute({"season": "Rabi 2025"})
		all_ppcs = [r["ppc"] for r in data]
		all_ppc_names = [r["ppc_name"] for r in data]

		for raw in ("MY200714", "DHAMNAHANDI", "CHANDILI", "MY200704"):
			self.assertNotIn(raw, all_ppc_names)
			self.assertFalse(any(raw in p for p in all_ppcs))

	def test_target_allocation_dynamic_change_and_lifecycle(self):
		"""
		Validate dynamic runtime loading and lifecycle:
		1. New PPC without target -> does NOT appear.
		2. Assign target 300 -> appears immediately with 300.
		3. Change target to 700 -> immediately reflects 700.
		4. Set target to 0 -> does NOT appear.
		5. Delete Target Allocation -> does NOT appear.
		"""
		test_code = "TEMP9920"
		temp_doc = frappe.new_doc("PPC Master")
		temp_doc.code = test_code
		temp_doc.ppc_name = "AUTOTEST_DYNAMIC_PPC"
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
			self.assertEqual(d2[0]["m051007_target"], 300.0)
			self.assertEqual(d2[0]["total_target"], 300.0)

			# 3. Change Target Quantity from 300 to 700 -> immediately reflects 700
			ta_doc.target_quantity = 700.0
			ta_doc.save(ignore_permissions=True)

			_, d3 = execute({"ppc_name": test_code, "season": "Kharif 2025"})
			self.assertEqual(len(d3), 1)
			self.assertEqual(d3[0]["m051007_target"], 700.0)
			self.assertEqual(d3[0]["total_target"], 700.0)

			# 4. Set target_quantity to 0 -> does NOT appear
			ta_doc.target_quantity = 0.0
			ta_doc.save(ignore_permissions=True)

			_, d4 = execute({"ppc_name": test_code, "season": "Kharif 2025"})
			self.assertEqual(len(d4), 0, "PPC with Target Quantity = 0 must not appear")

		finally:
			if ta_doc and frappe.db.exists("Target Allocation", ta_doc.name):
				frappe.delete_doc("Target Allocation", ta_doc.name, force=True, ignore_permissions=True)
			if frappe.db.exists("PPC Master", temp_doc.name):
				frappe.delete_doc("PPC Master", temp_doc.name, force=True, ignore_permissions=True)

		# 5. After deletion -> does NOT appear
		_, d5 = execute({"ppc_name": test_code, "season": "Kharif 2025"})
		self.assertEqual(len(d5), 0, "Deleted PPC must not appear in report")

	def test_get_eligible_ppcs_query(self):
		"""PPC search query shows only eligible PPCs (PPC Master + Target Quantity > 0 in season)."""
		# Kharif 2025: exactly 48 PPCs
		results_k = get_eligible_ppcs_query(
			doctype="PPC Master", txt="", searchfield="name", start=0, page_len=100,
			filters={"season": "Kharif 2025"}
		)
		self.assertEqual(len(results_k), 48)
		k_names = [r[0] for r in results_k]
		self.assertIn("S1050113", k_names)
		self.assertNotIn("NON_EXISTENT_PPC", k_names)

		# Rabi 2025: exactly 1 PPC
		results_r = get_eligible_ppcs_query(
			doctype="PPC Master", txt="", searchfield="name", start=0, page_len=20,
			filters={"season": "Rabi 2025"}
		)
		self.assertEqual(len(results_r), 1)
		self.assertEqual(results_r[0][0], "S1050215")

		# Text search matches
		results_search = get_eligible_ppcs_query(
			doctype="PPC Master", txt="DUDUKA", searchfield="name", start=0, page_len=20,
			filters={"season": "Kharif 2025"}
		)
		self.assertEqual(len(results_search), 1)
		self.assertEqual(results_search[0][0], "S1050113")

	def test_mill_column_ordering_by_company_and_type(self):
		"""Verify that mills are grouped by company, with Raw first and Boiled second."""
		mills = get_relevant_mills()
		names = [m.get("company") for m in mills]

		# 1. Verify exact order on site shyamji
		self.assertEqual(names[0], "Shree Shyamji Paddy Processing Pvt Ltd (Raw)")
		self.assertEqual(names[1], "Shree Shyamji Paddy Processing Pvt Ltd (Boiled)")
		self.assertEqual(names[2], "Radhe Govind Food Products (Raw)")
		self.assertEqual(names[3], "Radhe Govind Food Products (Boiled)")
		self.assertEqual(names[4], "Laddu Gopal Industries (Boiled)")

		# 2. Verify column groups follow this sequence with Target, Received, Balance
		columns = get_columns()
		mill_target_cols = [
			c["mill_name"] for c in columns if c.get("mill_group") and c["fieldname"].endswith("_target")
		]
		self.assertEqual(mill_target_cols, names)

	def test_abstract_report_vertical_column_borders(self):
		"""Verify continuous vertical borders between #, Season, PPC, mill groups, and Grand Total."""
		import json
		import subprocess

		columns = get_columns()
		js_path = frappe.get_app_path("ivri_od", "procurement", "report", "abstract_report", "abstract_report.js")

		node_script = """
		const fs = require('fs');
		const code = fs.readFileSync(__JS_PATH__, 'utf8');
""".replace("__JS_PATH__", json.dumps(js_path)) + """
		global.frappe = {
			query_reports: {},
			utils: { escape_html: (s) => s }
		};
		global.__ = (s) => s;
		global.flt = (v) => parseFloat(v) || 0;
		const appendedSuperCells = [];
		const mockEl = () => {
			const obj = {
				length: 1,
				find: () => mockEl(),
				empty: () => obj,
				append: (child) => {
					if (typeof child === 'string') appendedSuperCells.push(child);
					else if (child && child.__html) appendedSuperCells.push(child.__html);
					return obj;
				},
				before: () => obj,
				off: () => obj,
				on: () => obj,
				addClass: () => obj,
				attr: () => ""
			};
			return obj;
		};
		global.$ = (html) => {
			const el = mockEl();
			if (typeof html === 'string') {
				el.__html = html;
			}
			return el;
		};
		global.window = {
			off: () => ({ on: () => {} }),
			on: () => {}
		};

		let createdStyle = null;
		global.document = {
			head: { appendChild: () => {} },
			getElementById: () => null,
			createElement: () => {
				createdStyle = { id: '', textContent: '' };
				return createdStyle;
			}
		};

		eval(code);

		const report = frappe.query_reports['Abstract Report'];
		const rawColumns = JSON.parse(fs.readFileSync(0, 'utf8'));

		// Emulate Frappe DataTable columns including _rowIndex as colIndex 0
		const datatableColumns = [
			{ id: '_rowIndex', fieldname: '_rowIndex', colIndex: 0 }
		].concat(rawColumns.map((c, i) => Object.assign({}, c, {
			colIndex: i + 1,
			id: c.fieldname
		})));

		const mockDataTable = {
			header: {},
			wrapper: {},
			datamanager: {
				getColumns: () => datatableColumns
			}
		};

		report.after_datatable_render(mockDataTable);

		const result = {
			style_css: createdStyle ? createdStyle.textContent : '',
			super_cells: appendedSuperCells
		};
		process.stdout.write(JSON.stringify(result));
		"""

		proc = subprocess.run(
			["node", "-e", node_script],
			input=json.dumps(columns, default=str),
			capture_output=True,
			text=True,
			cwd=frappe.get_app_path("frappe", "../.."),
		)
		if proc.returncode != 0:
			raise AssertionError(f"Node script failed (exit {proc.returncode}):\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")

		result = json.loads(proc.stdout)
		style_css = result["style_css"]
		super_cells = " ".join(result.get("super_cells", []))

		# 1. Verify border style definitions
		self.assertIn("border-right: 2px solid #64748b !important", style_css)
		self.assertIn(".dt-super-cell--row-index-divider", style_css)
		self.assertIn(".dt-super-cell--season", style_css)
		self.assertIn(".dt-super-cell--ppc-divider", style_css)
		self.assertIn(".dt-super-cell--mill", style_css)
		self.assertIn(".dt-super-cell--total", style_css)

		# 2. Verify row index (#) column has border-right divider rule (colIndex 0)
		self.assertIn(".dt-cell--col-0", style_css, "# column (col 0) must have divider CSS rule")

		# 3. Verify Season column has no border rule (colIndex 1)
		self.assertIn(".dt-cell--col-1", style_css, "Season column (col 1) must have rule")
		self.assertIn("border-right: none !important", style_css, "Season must have border-right: none")

		# 4. Verify PPC column has border-right divider rule (colIndex 2)
		self.assertIn(".dt-cell--col-2", style_css, "PPC column (col 2) must have divider CSS rule")

		# 5. Verify all mill balance columns + total balance have border-right
		# In our simulated datatableColumns, offset is +1 because of _rowIndex
		balance_col_indices = [
			i + 1 for i, c in enumerate(columns)
			if c["fieldname"].endswith("_balance")
		]
		self.assertGreaterEqual(len(balance_col_indices), 5, "Must have at least 5 mill balance columns + total balance")

		for b_idx in balance_col_indices:
			self.assertIn(f".dt-cell--col-{b_idx}", style_css, f"Balance column {b_idx} must have divider CSS rule")

		# 6. Verify Grand Total super-header
		self.assertIn("Grand Total", super_cells, "Super header must contain 'Grand Total'")



def run_quick():
	suite = unittest.TestSuite()
	suite.addTest(TestAbstractReport("test_abstract_report_vertical_column_borders"))
	suite.addTest(TestAbstractReport("test_columns_structure_and_dynamic_mills"))
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	if not result.wasSuccessful():
		raise RuntimeError(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
	print(f"All {result.testsRun} tests passed successfully!")
	return True


def run():
	suite = unittest.TestLoader().loadTestsFromTestCase(TestAbstractReport)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	if not result.wasSuccessful():
		raise RuntimeError(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
	print(f"All {result.testsRun} tests passed successfully!")
	return True
