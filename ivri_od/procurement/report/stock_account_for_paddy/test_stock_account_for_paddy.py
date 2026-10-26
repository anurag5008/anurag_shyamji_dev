# Copyright (c) 2026, Profezzo and contributors

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	build_rows,
	classify,
	dcro_release,
	get_months,
	grn_receipts,
	season_code_from_pass_key,
	validate_filters,
)

FROM_DATE = getdate("2025-11-01")


def grn(key, receipt_date, net_weight):
	return frappe._dict(pass_unique_key=key, receipt_date=receipt_date, net_weight=net_weight)


# GRNs in receipt order.
GRNS = [
	# TP-1 (100 QT): 60 in October (before the period), 50 in November -> fulfilled, counts 100.
	grn("M1-P(S1)-K25-TP1", "2025-10-20", 60),
	grn("M1-P(S1)-K25-TP1", "2025-11-03", 50),
	# TP-2 (80 QT): two trucks in November, 30 + 30 -> short, counts 60.
	grn("M1-P(S1)-K25-TP2", "2025-11-05", 30),
	grn("M1-P(S1)-K25-TP2", "2025-11-06", 30),
	# TP-3 (50 QT): 49.5 in November, 3 more in January -> fulfilled, counts 50.
	grn("M1-P(S1)-K25-TP3", "2025-11-20", 49.5),
	grn("M1-P(S1)-K25-TP3", "2026-01-04", 3),
]
TP_QUANTITIES = {"M1-P(S1)-K25-TP1": 100, "M1-P(S1)-K25-TP2": 80, "M1-P(S1)-K25-TP3": 50}

DCRO_ROW = {
	"RO No.": "RO1",
	"Date of Requistion": "15-11-2025",
	"Paddy Lifted (Own District) (in Qtl)": "500.00",
	"Quantity of Paddy Released for Milling (Own District) (in Qtl)": "70.00",
	"Quantity of Paddy Released for Milling (Other District) (in Qtl)": "5.50",
	"Status of Released Order": "Approved",
}
SKIP = ["reject", "cancel"]


class TestStockAccountForPaddy(IntegrationTestCase):
	def get_rows(self):
		movements = grn_receipts(GRNS, TP_QUANTITIES)
		movements.append(dcro_release(DCRO_ROW, SKIP))
		movements.append((getdate("2025-10-25"), "issue_for_milling", 10))
		opening, by_month = classify(movements, FROM_DATE)
		return build_rows(get_months(FROM_DATE, getdate("2026-01-31")), opening, by_month)

	def test_pacs_counts_tp_quantity_once_fulfilled(self):
		receipts = [qty for _date, _column, qty in grn_receipts(GRNS, TP_QUANTITIES)]
		self.assertEqual(receipts, [60, 40, 30, 30, 49.5, 0.5])

	def test_dcro_release(self):
		self.assertEqual(dcro_release(DCRO_ROW, SKIP), (getdate("2025-11-15"), "issue_for_milling", 75.5))
		self.assertIsNone(dcro_release({**DCRO_ROW, "Status of Released Order": "Rejected"}, SKIP))
		self.assertIsNone(dcro_release({**DCRO_ROW, "Date of Requistion": ""}, SKIP))

	def test_months_ob_cb(self):
		rows = self.get_rows()
		month_rows = rows[:-1]

		self.assertEqual([row["month"] for row in month_rows], ["Nov-25", "Dec-25", "Jan-26"])
		# OB: 60 received in October - 10 released in October.
		self.assertEqual(month_rows[0]["ob"], 50)
		november = month_rows[0]
		self.assertEqual((november["pacs"], november["wshgs"], november["other_rect"]), (149.5, 0, 0))
		self.assertEqual(november["total_paddy"], 199.5)
		self.assertEqual((november["issue_for_milling"], november["driage"], november["total"]), (75.5, 0, 75.5))
		self.assertEqual(november["cb"], 124)

		for previous, current in zip(month_rows, month_rows[1:]):
			self.assertEqual(current["ob"], previous["cb"])
		for row in rows:
			self.assertEqual(row["cb"], round(row["total_paddy"] - row["total"], 2))
		self.assertEqual(month_rows[1]["pacs"], 0)
		self.assertEqual(month_rows[2]["pacs"], 0.5)

	def test_total_row(self):
		rows = self.get_rows()
		month_rows, total_row = rows[:-1], rows[-1]

		self.assertTrue(total_row["bold"])
		self.assertEqual(total_row["ob"], month_rows[0]["ob"])
		for field in ("pacs", "wshgs", "other_rect", "issue_for_milling", "driage", "total"):
			self.assertEqual(total_row[field], round(sum(row[field] for row in month_rows), 2))
		self.assertEqual(total_row["total_paddy"], round(total_row["ob"] + total_row["pacs"], 2))
		self.assertEqual(total_row["cb"], month_rows[-1]["cb"])

	def test_season_code_from_pass_key(self):
		self.assertEqual(season_code_from_pass_key("M051007-BAKTI(S1050104)-K25-TP45"), "K25")
		self.assertEqual(season_code_from_pass_key(""), "")

	def test_from_month_after_to_month(self):
		filters = frappe._dict(
			mill="MILL",
			kms_season="KMS",
			paddy_account="DISTRICT",
			from_month="2025-02-10",
			to_month="2025-01-20",
		)
		with patch("frappe.db.get_value", return_value="_Test Company"):
			self.assertRaises(frappe.ValidationError, validate_filters, filters)

			filters.to_month = "2025-02-01"
			self.assertEqual(validate_filters(filters), (getdate("2025-02-01"), getdate("2025-02-28")))
		# Company comes from the mill.
		self.assertEqual(filters.company, "_Test Company")
