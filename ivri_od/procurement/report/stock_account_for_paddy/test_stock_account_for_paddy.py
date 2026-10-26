# Copyright (c) 2026, Profezzo and contributors

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	build_rows,
	classify,
	get_months,
	validate_filters,
)

FROM_DATE = getdate("2024-11-01")


def sle(voucher_no, posting_date, qty, voucher_type="Stock Entry", source=None, movement=None):
	return frappe._dict(
		voucher_type=voucher_type,
		voucher_no=voucher_no,
		posting_date=posting_date,
		actual_qty=qty,
		stock_uom="Quintal",
		paddy_source=source,
		paddy_movement=movement,
	)


LEDGER = [
	# Before the period: goes into the first OB.
	sle("PR-OLD", "2024-10-15", 50, "Purchase Receipt", "PACS"),
	sle("MILL-OLD", "2024-10-20", -10, movement="Issue for Milling"),
	# November
	sle("PR-1", "2024-11-05", 100.25, "Purchase Receipt", "PACS"),
	sle("PR-2", "2024-11-06", 40, "Purchase Receipt", "WSHG"),
	sle("SE-RECEIPT", "2024-11-07", 5, source=None),
	sle("MILL-1", "2024-11-10", -60.5, movement="Issue for Milling"),
	sle("DRIAGE-1", "2024-11-30", -0.75, movement="Driage"),
	# December: no movement. January
	sle("PR-RETURN", "2025-01-03", -4, "Purchase Receipt", "WSHG"),
	sle("PR-3", "2025-01-04", 30, "Purchase Receipt", "WSHG"),
	# Transfer between two selected warehouses nets to zero.
	sle("TRANSFER", "2025-01-08", -20),
	sle("TRANSFER", "2025-01-08", 20),
	# Milling done as a transfer to a milling warehouse: only the outgoing leg counts.
	sle("MILL-2", "2025-01-09", -25, movement="Issue for Milling"),
	sle("MILL-2", "2025-01-09", 25, movement="Issue for Milling"),
	# Paddy going out through an entry type with no Paddy Movement.
	sle("SE-SALE", "2025-01-10", -3),
]


class TestStockAccountForPaddy(IntegrationTestCase):
	def get_rows(self):
		opening, movements, unclassified = classify(LEDGER, FROM_DATE)
		return build_rows(get_months(FROM_DATE, getdate("2025-01-31")), opening, movements), unclassified

	def test_every_month_shown_with_ob_from_previous_cb(self):
		rows, _unclassified = self.get_rows()
		month_rows, total_row = rows[:-1], rows[-1]

		self.assertEqual([row["month"] for row in month_rows], ["Nov-24", "Dec-24", "Jan-25"])
		self.assertEqual(month_rows[0]["ob"], 40)
		for previous, current in zip(month_rows, month_rows[1:]):
			self.assertEqual(current["ob"], previous["cb"])
		for row in rows:
			self.assertEqual(row["cb"], round(row["total_paddy"] - row["total"], 2))

		december = month_rows[1]
		self.assertEqual(
			[december[f] for f in ("pacs", "wshgs", "other_rect", "issue_for_milling", "driage")], [0] * 5
		)
		self.assertTrue(total_row["bold"])

	def test_columns(self):
		rows, unclassified = self.get_rows()
		november, january = rows[0], rows[2]

		self.assertEqual((november["pacs"], november["wshgs"], november["other_rect"]), (100.25, 40, 5))
		self.assertEqual(november["total_paddy"], 185.25)
		self.assertEqual(
			(november["issue_for_milling"], november["driage"], november["total"]), (60.5, 0.75, 61.25)
		)
		self.assertEqual(november["cb"], 124)

		self.assertEqual((january["wshgs"], january["other_rect"]), (26, 0))
		self.assertEqual(january["issue_for_milling"], 25)
		self.assertEqual([voucher.voucher_no for voucher in unclassified], ["SE-SALE"])

	def test_total_row(self):
		rows, _unclassified = self.get_rows()
		month_rows, total_row = rows[:-1], rows[-1]

		self.assertEqual(total_row["ob"], month_rows[0]["ob"])
		for field in ("pacs", "wshgs", "other_rect", "issue_for_milling", "driage", "total"):
			self.assertEqual(total_row[field], round(sum(row[field] for row in month_rows), 2))
		receipts = total_row["pacs"] + total_row["wshgs"] + total_row["other_rect"]
		self.assertEqual(total_row["total_paddy"], round(total_row["ob"] + receipts, 2))
		self.assertEqual(total_row["cb"], month_rows[-1]["cb"])

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
