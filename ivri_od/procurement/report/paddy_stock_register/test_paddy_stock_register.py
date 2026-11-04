# Copyright (c) 2026, Profezzo and contributors

from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.report.paddy_stock_register.paddy_stock_register import (
	ISSUE_FOR_MILLING,
	RECEIPT_PACS,
	RECEIPT_SHG,
	RELEASE_ORDER,
	build_rows,
	get_columns,
	pvr_days,
	split_milling,
)

SEASON_START = "2025-10-01"
FROM_DATE = "2025-12-01"

# Sample (masked) data. Before From Date: receipts 75772.41 + 2761.61, issued 55000
# -> O.B. on From Date 23534.02. Day 1: issue 800 -> C.B. 22734.02.
MOVEMENTS = [
	("2025-09-30", RECEIPT_PACS, 999),  # before the season start: ignored
	("2025-10-10", RECEIPT_PACS, 75772.41),
	("2025-10-15", RECEIPT_SHG, 2761.61),
	("2025-11-20", ISSUE_FOR_MILLING, 55000),
	("2025-11-25", RELEASE_ORDER, 1000),
	("2025-12-01", ISSUE_FOR_MILLING, 800),
	("2025-12-03", RECEIPT_PACS, 100),
	("2025-12-03", RELEASE_ORDER, 500),
]


class TestPaddyStockRegister(IntegrationTestCase):
	def setUp(self):
		self.rows = build_rows(SEASON_START, FROM_DATE, "2025-12-03", 0, MOVEMENTS)

	def test_one_row_per_day(self):
		self.assertEqual([r.date for r in self.rows], [getdate(f"2025-12-0{d}") for d in (1, 2, 3)])

	def test_day_one_sample(self):
		day1 = self.rows[0]
		self.assertEqual(day1.ob, 23534.02)
		self.assertEqual(day1.prog_receipt_pacs, 75772.41)
		self.assertEqual(day1.prog_receipt_shg, 2761.61)
		self.assertEqual(day1.prog_receipt_total, 78534.02)
		self.assertEqual(day1.issue_for_milling, 800)
		self.assertEqual(day1.prog_issue_for_milling, 55800)
		self.assertEqual(day1.total_disposal, 55800)
		self.assertEqual(day1.cb, 22734.02)
		self.assertEqual(day1.mismatch, 0)

	def test_empty_day(self):
		day2 = self.rows[1]
		self.assertEqual(day2.ob, 22734.02)  # previous day's C.B.
		self.assertEqual(day2.receipt_pacs, 0)  # receipts show 0.00
		self.assertIsNone(day2.issue_for_milling)  # blank, not 0.00
		self.assertIsNone(day2.release_order)
		self.assertEqual(day2.cb, 22734.02)

	def test_release_order_is_not_stock(self):
		day3 = self.rows[2]
		self.assertEqual(day3.release_order, 500)
		self.assertEqual(day3.prog_release_order, 1500)
		self.assertEqual(day3.total_stock, 22834.02)
		self.assertEqual(day3.cb, 22834.02)
		self.assertTrue(all(not r.mismatch for r in self.rows))

	def test_season_opening(self):
		rows = build_rows(SEASON_START, FROM_DATE, FROM_DATE, 1000, MOVEMENTS)
		self.assertEqual(rows[0].ob, 24534.02)
		self.assertEqual(rows[0].cb, 23734.02)
		self.assertEqual(rows[0].mismatch, 0)

	def test_column_order(self):
		self.assertEqual(
			[c["fieldname"] for c in get_columns()],
			[
				"date", "ob", "receipt_pacs", "receipt_shg", "total_stock", "prog_receipt_pacs", "prog_receipt_shg",
				"prog_receipt_total", "release_order", "prog_release_order", "issue_for_milling",
				"prog_issue_for_milling", "total_disposal", "cb",
			],
		)


class TestMillingSplit(IntegrationTestCase):
	def test_pvr_days(self):
		# 2nd PVR, 06-05 -> 08-05: 06-05 and 07-05
		self.assertEqual(pvr_days("2026-05-06", "2026-05-08"), [getdate("2026-05-06"), getdate("2026-05-07")])
		# 03-02 -> 06-02: the 3rd, 4th and 5th
		self.assertEqual(
			pvr_days("2026-02-03", "2026-02-06"), [getdate(f"2026-02-0{d}") for d in (3, 4, 5)]
		)
		# First PVR (present 06-05): only the day before, 05-05
		self.assertEqual(pvr_days(None, "2026-05-06"), [getdate("2026-05-05")])

	def test_split_adds_up_and_keeps_minimum(self):
		days = pvr_days("2026-02-01", "2026-02-08")  # 7 days
		for total in (5200, 2600.55, 1600, 6400):
			split = split_milling(total, days, 400, f"MVR-{total}")
			self.assertAlmostEqual(sum(q for _, q in split), total, places=2)
			self.assertTrue(all(q >= 400 for _, q in split))
			self.assertTrue(all(d in days for d, _ in split))
			self.assertEqual(len({d for d, _ in split}), len(split))  # one entry per day

	def test_whole_numbers(self):
		days = pvr_days("2026-05-08", "2026-05-26")
		for total in (6400, 5200, 3500, 2600, 1600):
			split = split_milling(total, days, 400, f"MVR-{total}")
			self.assertTrue(all(q == int(q) for _, q in split), split)
			self.assertEqual(sum(q for _, q in split), total)
		# Decimals in the PVR quantity stay only on the last day
		split = split_milling(2600.55, days, 400, "MVR-D")
		self.assertTrue(all(q == int(q) for _, q in split[:-1]))
		self.assertAlmostEqual(sum(q for _, q in split), 2600.55, places=2)

	def test_small_week(self):
		# 600 over 3 days with minimum 400: only one day can have milling
		split = split_milling(600, pvr_days("2026-02-03", "2026-02-06"), 400, "MVR-X")
		self.assertEqual(len(split), 1)
		self.assertEqual(split[0][1], 600)
		# Below the minimum: all on one day
		self.assertEqual(split_milling(250, pvr_days("2026-02-03", "2026-02-06"), 400, "MVR-Y")[0][1], 250)

	def test_same_split_every_run(self):
		days = pvr_days("2026-02-01", "2026-02-08")
		self.assertEqual(split_milling(5200, days, 400, "MVR-1"), split_milling(5200, days, 400, "MVR-1"))


class TestNoSeasonStartDate(IntegrationTestCase):
	def test_counts_every_movement_without_start_date(self):
		# Season Master without Start Date: the movement of 2025-09-30 is counted too.
		rows = build_rows(None, FROM_DATE, FROM_DATE, 0, MOVEMENTS)
		self.assertEqual(rows[0].prog_receipt_pacs, 75772.41 + 999)
		self.assertEqual(rows[0].ob, 23534.02 + 999)
		self.assertEqual(rows[0].mismatch, 0)
