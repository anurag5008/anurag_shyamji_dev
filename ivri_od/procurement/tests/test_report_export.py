# Copyright (c) 2026, Profezzo and contributors

import csv
import io

import frappe
from frappe.tests import IntegrationTestCase

from ivri_od.procurement.report_export import _export_query, add_serial_numbers, filter_rows, is_app_report

COLUMNS = [
	{"label": "Lot No.", "fieldname": "lot", "fieldtype": "Data"},
	{"label": "Weight", "fieldname": "weight", "fieldtype": "Float"},
]
ROWS = [{"lot": f"L{n}", "weight": 10.0 * n} for n in range(1, 6)]


class TestReportExport(IntegrationTestCase):
	def test_only_filtered_rows_numbered_from_one(self):
		columns, rows = [dict(c) for c in COLUMNS], filter_rows([dict(r) for r in ROWS], COLUMNS, [1, 3, 4])
		add_serial_numbers(columns, rows)
		self.assertEqual(columns[0]["label"], "Sl No")
		self.assertEqual([(r["sl_no"], r["lot"]) for r in rows], [(1, "L2"), (2, "L4"), (3, "L5")])

	def test_total_row_made_again_and_not_numbered(self):
		rows = [dict(r) for r in ROWS] + [{"lot": "", "weight": 150.0}]
		rows = filter_rows(rows, COLUMNS, [0, 2], has_total_row=True)
		add_serial_numbers([dict(c) for c in COLUMNS], rows, has_total_row=True)
		self.assertEqual([r["sl_no"] for r in rows[:-1]], [1, 2])
		self.assertEqual(rows[-1][0], "")  # total row (a list) gets a blank Sl No
		self.assertEqual(rows[-1][2], 40.0)  # total of the filtered rows only

	def test_no_filter_keeps_all_rows(self):
		self.assertEqual(len(filter_rows(ROWS, COLUMNS, [])), 5)
		self.assertEqual(len(filter_rows(ROWS, COLUMNS, [0, 1, 2, 3, 4])), 5)

	def test_report_own_total_row_not_numbered(self):
		rows = [{"month": "Nov-25"}, {"month": "Dec-25"}, {"month": "TOTAL"}]
		add_serial_numbers([{"fieldname": "month"}], rows)
		self.assertEqual([r["sl_no"] for r in rows], [1, 2, ""])

	def test_list_rows(self):
		rows = [["L1", 1.0], ("L2", 2.0)]
		add_serial_numbers([dict(c) for c in COLUMNS], rows)
		self.assertEqual(rows, [[1, "L1", 1.0], [2, "L2", 2.0]])

	def test_app_reports_only(self):
		self.assertTrue(is_app_report("DC Transit Challan from DCRO"))
		if frappe.db.exists("Report", "General Ledger"):
			self.assertFalse(is_app_report("General Ledger"))
		self.assertFalse(is_app_report(None))

	def test_csv_of_filtered_report(self):
		report = "DC Transit Challan from DCRO"
		params = frappe._dict(
			report_name=report, file_format_type="CSV", filters={}, visible_idx=[2, 5], applied_filters={}
		)
		csv_params = {"delimiter": ",", "quoting": csv.QUOTE_NONNUMERIC, "decimal_sep": "."}
		_name, extension, content = _export_query(params, csv_params, populate_response=False)
		lines = list(csv.reader(io.StringIO(content.decode())))
		if len(lines) < 3:
			self.skipTest("Needs at least 6 DC Transit Challan rows")
		self.assertEqual(extension, "csv")
		self.assertEqual(lines[0][0], "Sl No")
		self.assertEqual([line[0] for line in lines[1:]], ["1", "2"])
