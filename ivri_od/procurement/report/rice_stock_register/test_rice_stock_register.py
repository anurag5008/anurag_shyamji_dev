# Copyright (c) 2026, Profezzo and contributors

from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.report.rice_stock_register.rice_stock_register import (
	DELIVERY_FCI,
	DELIVERY_RRC,
	RECEIPT_FROM_MILLING,
	build_rows,
	get_columns,
	negative_cb_warnings,
)

SEASON_START = "2025-10-01"
FROM_DATE = "2025-12-01"

# Sample (masked) data. Before Day 1: receipt 37400, FCI 20253.8200, RRC 10137.1280
# -> O.B. 7009.0520. Day 1: receipt 544, FCI 289.7360 -> C.B. 7263.3160, Total Prog 30680.6840.
MOVEMENTS = [
	("2025-09-30", RECEIPT_FROM_MILLING, 999),  # before the season start: ignored
	("2025-10-20", RECEIPT_FROM_MILLING, 37400),
	("2025-11-10", DELIVERY_FCI, 20253.82),
	("2025-11-15", DELIVERY_RRC, 10137.128),
	("2025-12-01", RECEIPT_FROM_MILLING, 544),
	("2025-12-01", DELIVERY_FCI, 289.736),
]


class TestRiceStockRegister(IntegrationTestCase):
	def setUp(self):
		self.rows = build_rows(SEASON_START, FROM_DATE, "2025-12-02", 0, MOVEMENTS)

	def test_day_one_sample(self):
		day1 = self.rows[0]
		self.assertEqual(day1.date, getdate(FROM_DATE))
		self.assertEqual(day1.ob, 7009.052)
		self.assertEqual(day1.receipt_from_milling, 544)
		self.assertEqual(day1.total_stock, 7553.052)
		self.assertEqual(day1.prog_receipt, 37944)
		self.assertEqual(day1.delivery_fci, 289.736)
		self.assertEqual(day1.delivery_rrc, 0)  # 0.0000, not blank
		self.assertEqual(day1.prog_delivery_fci, 20543.556)
		self.assertEqual(day1.prog_delivery_rrc, 10137.128)
		self.assertEqual(day1.total_prog_delivery, 30680.684)
		self.assertEqual(day1.cb, 7263.316)
		self.assertEqual(day1.mismatch, 0)

	def test_empty_day(self):
		day2 = self.rows[1]
		self.assertEqual(day2.ob, 7263.316)  # previous day's C.B.
		self.assertEqual(day2.receipt_from_milling, 0)
		self.assertEqual(day2.delivery_fci, 0)
		self.assertEqual(day2.cb, 7263.316)
		self.assertEqual(day2.mismatch, 0)

	def test_negative_cb_warning(self):
		self.assertEqual(negative_cb_warnings(self.rows), [])
		rows = build_rows(SEASON_START, FROM_DATE, FROM_DATE, 0, [(FROM_DATE, DELIVERY_FCI, 10)])
		self.assertEqual(rows[0].cb, -10)
		self.assertEqual(len(negative_cb_warnings(rows)), 1)

	def test_column_order(self):
		self.assertEqual(
			[c["fieldname"] for c in get_columns()],
			[
				"date", "ob", "receipt_from_milling", "total_stock", "prog_receipt", "delivery_fci",
				"delivery_rrc", "prog_delivery_fci", "prog_delivery_rrc", "total_prog_delivery", "cb",
			],
		)


class TestReceiptFromMilling(IntegrationTestCase):
	def test_paddy_milled_times_cmr_percentage(self):
		# Paddy Stock Register's Issue for Milling x CMR % (68) of Rice Delivery Setup, day by day.
		from unittest.mock import patch

		import frappe

		from ivri_od.procurement.report.rice_stock_register import rice_stock_register as module

		milled = [(getdate("2025-12-01"), "issue_for_milling", 800), (getdate("2025-12-02"), "issue_for_milling", 400.5)]
		with (
			patch.object(module, "get_rice_percentage", return_value=68),
			patch.object(module, "get_issue_for_milling", return_value=milled),
		):
			receipts = module.get_receipts_from_milling(frappe._dict(mill="M-TEST"), getdate("2025-12-02"))
		self.assertEqual(
			receipts,
			[(getdate("2025-12-01"), RECEIPT_FROM_MILLING, 544.0), (getdate("2025-12-02"), RECEIPT_FROM_MILLING, 272.34)],
		)
