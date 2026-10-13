# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import json
import os
import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from ivri_od.procurement.report.entry_report.entry_report import (
	execute,
	get_columns,
	get_data,
)


class TestEntryReport(FrappeTestCase):
	def test_columns_structure_and_order(self):
		"""Columns must exactly match the 9 required columns in order, with no Date or PACS Name."""
		columns = get_columns()
		self.assertEqual(len(columns), 9, "Entry Report must have exactly 9 columns")

		labels = [c["label"] for c in columns]
		fieldnames = [c["fieldname"] for c in columns]

		expected_labels = [
			"Season",
			"PPC",
			"TP No.",
			"TP Qty (QTL)",
			"Mill Name",
			"Agent Name",
			"Entry Qty (QTL)",
			"Entry Price",
			"Total Amount",
		]
		self.assertEqual(labels, expected_labels)

		expected_fieldnames = [
			"season",
			"ppc",
			"tp_no",
			"tp_qty",
			"mill_name",
			"agent_name",
			"entry_qty",
			"entry_price",
			"total_amount",
		]
		self.assertEqual(fieldnames, expected_fieldnames)

		# Check critical exclusions
		for c in columns:
			label_lower = c["label"].lower()
			fn_lower = c["fieldname"].lower()
			self.assertNotIn("date", label_lower, "Report must not contain Date column")
			self.assertNotIn("date", fn_lower, "Report must not contain Date fieldname")
			self.assertNotIn("pacs", label_lower, "Report must not contain PACS Name column")
			self.assertNotIn("pacs", fn_lower, "Report must not contain PACS fieldname")

		# Check types and options
		self.assertEqual(columns[0]["fieldtype"], "Link")
		self.assertEqual(columns[0]["options"], "Season Master")
		self.assertEqual(columns[1]["fieldtype"], "Link")
		self.assertEqual(columns[1]["options"], "PPC Master")
		self.assertEqual(columns[2]["fieldtype"], "Data")
		self.assertEqual(columns[3]["fieldtype"], "Float")
		self.assertEqual(columns[3]["precision"], 3)
		self.assertEqual(columns[4]["fieldtype"], "Data")
		self.assertEqual(columns[5]["fieldtype"], "Data")
		self.assertEqual(columns[6]["fieldtype"], "Float")
		self.assertEqual(columns[6]["precision"], 3)
		self.assertEqual(columns[7]["fieldtype"], "Float")
		self.assertEqual(columns[7]["precision"], 2)
		self.assertEqual(columns[8]["fieldtype"], "Float")
		self.assertEqual(columns[8]["precision"], 2)

	def test_report_json_metadata(self):
		"""Verify report is not a prepared/background report and references Entry doctype."""
		json_path = os.path.join(
			frappe.get_app_path("ivri_od"),
			"procurement",
			"report",
			"entry_report",
			"entry_report.json",
		)
		self.assertTrue(os.path.exists(json_path), "entry_report.json must exist")
		with open(json_path, encoding="utf-8") as f:
			meta = json.load(f)

		self.assertEqual(meta.get("prepared_report"), 0, "prepared_report must be 0")
		self.assertEqual(meta.get("ref_doctype"), "Entry", "ref_doctype must be Entry")
		self.assertEqual(meta.get("add_total_row"), 1, "add_total_row must be 1")

	def test_existing_entry_data_and_calculations(self):
		"""Verify execution returns existing EN-2026-00001 entry row with correct values."""
		cols, data = execute({})
		self.assertGreaterEqual(len(data), 1, "Should have at least 1 entry row")

		row = next((r for r in data if r.get("tp_no") == "139"), None)
		self.assertIsNotNone(row, "Row for TP 139 should exist")

		self.assertEqual(row["season"], "Kharif 2025")
		self.assertEqual(row["ppc"], "DUDUKA(S1050113)")
		self.assertEqual(row["tp_no"], "139")
		self.assertEqual(flt(row["tp_qty"]), 166.98)
		self.assertEqual(row["mill_name"], "Shree Shyamji Paddy Processing Pvt Ltd (Boiled)")
		self.assertEqual(row["agent_name"], "Arjun")
		self.assertEqual(flt(row["entry_qty"]), 50.0)
		self.assertEqual(flt(row["entry_price"]), 2300.0)
		self.assertEqual(flt(row["total_amount"]), 115000.0)

	def test_filters(self):
		"""Verify filter behavior on Season, PPC, and Mill."""
		# Matching season
		_, data_s1 = execute({"season": "Kharif 2025"})
		self.assertGreaterEqual(len(data_s1), 1)

		# Non-matching season
		_, data_s2 = execute({"season": "Rabi 2025"})
		self.assertEqual(len(data_s2), 0)

		# Matching mill
		_, data_m1 = execute({"mill_name": "M051007"})
		self.assertGreaterEqual(len(data_m1), 1)

		# Non-matching mill
		_, data_m2 = execute({"mill_name": "M050410"})
		self.assertEqual(len(data_m2), 0)

		# Matching PPC
		_, data_p1 = execute({"ppc_name": "S1050113"})
		self.assertGreaterEqual(len(data_p1), 1)

		# Non-matching PPC
		_, data_p2 = execute({"ppc_name": "S1050812"})
		self.assertEqual(len(data_p2), 0)

	def test_query_report_run(self):
		"""Verify desk query_report.run works directly and is not a background report."""
		from frappe.desk.query_report import run as qr_run

		res = qr_run("Entry Report", filters={})
		self.assertIn("columns", res)
		self.assertIn("result", res)
		self.assertIsNone(res.get("status"), "Should not be a background/queued report")
		self.assertTrue(res.get("add_total_row"))

	def test_procurement_workspace_integration(self):
		"""Verify Entry Report is present in Procurement Workspace under Reports card."""
		ws = frappe.get_doc("Workspace", "Procurement")
		report_links = [
			l.link_to
			for l in ws.links
			if l.type == "Link" and l.link_type == "Report"
		]
		self.assertIn("Entry Report", report_links, "Entry Report must be in Procurement Workspace links")


def run():
	suite = unittest.TestLoader().loadTestsFromTestCase(TestEntryReport)
	runner = unittest.TextTestRunner(verbosity=2)
	result = runner.run(suite)
	if not result.wasSuccessful():
		raise RuntimeError(f"Tests failed: {len(result.failures)} failures, {len(result.errors)} errors")
	print(f"All {result.testsRun} tests passed successfully!")
	return True
