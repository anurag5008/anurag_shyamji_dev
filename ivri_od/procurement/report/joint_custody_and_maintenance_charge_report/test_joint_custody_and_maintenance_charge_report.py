# Copyright (c) 2026, Profezzo and contributors

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ivri_od.procurement.report.joint_custody_and_maintenance_charge_report.joint_custody_and_maintenance_charge_report import (
	build_rows,
	get_kms_months,
	get_summary,
	get_total_row,
	validate_filters,
)

MODULE = "ivri_od.procurement.report.joint_custody_and_maintenance_charge_report.joint_custody_and_maintenance_charge_report"

# Paper statement KMS 2024-25 (PACS receipts and issues, no transfer), rate 2.40.
SAMPLE = {
	"Dec-24": (39642.44, 0),
	"Jan-25": (45407.50, 24900.00),
	"Feb-25": (3302.05, 12600.00),
	"Mar-25": (0, 13700.00),
	"Apr-25": (0, 8900.00),
	"May-25": (1620.16, 14000.00),
	"Jun-25": (7094.04, 5200.00),
	"Jul-25": (0, 2600.00),
	"Aug-25": (0, 8714.20),
	"Sep-25": (0, 6451.99),
}


def sample_rows():
	months = get_kms_months("24-25")
	movements = {}
	for month in months:
		pacs, issue = SAMPLE.get(month.strftime("%b-%y"), (0, 0))
		movements[month] = {"transfer": 0, "pacs": pacs, "issue": issue}
	return build_rows(months, 0, movements)


class TestJointCustodyAndMaintenanceChargeReport(IntegrationTestCase):
	def test_kms_months_run_nov_to_oct(self):
		months = [m.strftime("%b-%y") for m in get_kms_months("24-25")]
		self.assertEqual(len(months), 12)
		self.assertEqual(months[0], "Nov-24")
		self.assertEqual(months[-1], "Oct-25")

	def test_rows_match_paper_statement(self):
		rows = {row["month"]: row for row in sample_rows()}
		self.assertEqual(rows["Jan-25"]["ob"], 39642.44)
		self.assertEqual(rows["Jan-25"]["cb"], 60149.94)
		self.assertEqual(rows["May-25"]["cb"], 15872.15)
		self.assertEqual(rows["Aug-25"]["cb"], 6451.99)
		self.assertEqual(rows["Sep-25"]["cb"], 0)
		self.assertEqual(rows["Oct-25"]["ob"], 0)

	def test_total_row_leaves_balances_blank(self):
		total = get_total_row(sample_rows())
		self.assertIsNone(total["ob"])
		self.assertIsNone(total["total"])
		self.assertIsNone(total["cb"])
		self.assertEqual(total["pacs"], 97066.19)
		self.assertEqual(total["ob_cb"], 542609.74)

	def test_summary_matches_paper_statement(self):
		summary = get_summary(sample_rows(), 2.40)
		self.assertEqual(summary["average_paddy"], 271304.87)
		self.assertEqual(summary["received"], 97066.19)
		self.assertEqual(summary["average_period"], 2.795)
		self.assertEqual(summary["due_per_qtl"], 6.71)
		self.assertEqual(summary["payable"], 651314)

	def test_no_receipt_gives_zero_not_error(self):
		months = get_kms_months("24-25")
		summary = get_summary(build_rows(months, 0, {}), 2.40)
		self.assertEqual(summary["average_period"], 0)
		self.assertEqual(summary["payable"], 0)

	@patch(f"{MODULE}.get_kms_years", return_value=["24-25"])
	def test_months_are_taken_whole_in_any_year(self, _years):
		# KMS 24-25, but months of 2027 may be chosen too.
		filters = frappe._dict(
			mill="M1", kms_year="24-25", district="D1", from_month="2027-01-01", to_month="2027-03-01"
		)
		self.assertEqual(validate_filters(filters), (date(2027, 1, 1), date(2027, 3, 31)))

	@patch(f"{MODULE}.get_kms_years", return_value=["24-25"])
	def test_from_month_after_to_month_is_refused(self, _years):
		filters = frappe._dict(
			mill="M1", kms_year="24-25", district="D1", from_month="2025-03-01", to_month="2025-01-31"
		)
		self.assertRaises(frappe.ValidationError, validate_filters, filters)
