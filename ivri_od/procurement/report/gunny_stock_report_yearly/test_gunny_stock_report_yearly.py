# Copyright (c) 2026, Profezzo and contributors

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.report.gunny_stock_report_yearly.gunny_stock_report_yearly import (
	build_rows,
	get_columns,
	get_total_row,
	set_value,
	shows_oscsc,
	transfer_receipts,
)
from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import get_months

DEC, JAN, FEB, MAR = (getdate(d) for d in ("2024-12-01", "2025-01-01", "2025-02-01", "2025-03-01"))


class TestGunnyStockReportYearly(IntegrationTestCase):
	def test_columns_in_order(self):
		labels = [column["label"] for column in get_columns()]
		self.assertEqual(len(labels), 14)
		self.assertEqual(labels[0], "Month")
		self.assertEqual(labels[5], "Actual Cost of Old Bags Procured")
		self.assertEqual(labels[-1], "Actual Cost of Unused Bags")

	def test_month_rows_without_movements(self):
		rows = build_rows(get_months(getdate("2024-09-01"), getdate("2025-11-30")), {})
		self.assertEqual(len(rows), 15)  # Sep-24 to Nov-25
		self.assertEqual((rows[0]["month"], rows[-1]["month"]), ("Sep-24", "Nov-25"))
		self.assertEqual(rows[3]["new_unused"], 0)

	def test_client_sheet_checks(self):
		movements = {
			DEC: {"old_procured": 148445, "old_used": 105713},
			JAN: {"oscsc": 39500, "new_used_cmr": 23780},
			MAR: {"old_procured": 10400},
		}
		rows = build_rows([DEC, JAN, FEB, MAR], movements)
		self.assertEqual(rows[0]["old_unused"], 42732)  # 0 + 148445 - 105713
		self.assertEqual(rows[1]["old_carried"], 42732)  # carried over = unused of the month before
		self.assertEqual(rows[2]["oscsc_ob"], 15720)  # month without movements
		self.assertEqual(rows[3]["old_unused"], 42732 + 10400)
		# Jan-25 of the sheet: 25000 + 39500 + 0 - 0 - 23780 = 40720; Nov-25: 125511 - 123959 - 1552 = 0.
		jan = build_rows([JAN], {JAN: {"oscsc": 39500, "new_used_cmr": 23780}})
		self.assertEqual(25000 + jan[0]["new_unused"], 40720)
		nov = build_rows([DEC, JAN], {DEC: {"oscsc": 125511}, JAN: {"tr_issue": 123959, "new_used_cmr": 1552}})
		self.assertEqual(nov[1]["new_unused"], 0)

	def test_total_row_sums_three_columns_only(self):
		rows = build_rows([DEC, JAN], {DEC: {"paddy_qtl": 10.25, "old_used": 5}, JAN: {"new_used_cmr": 7}})
		total = get_total_row(rows)
		self.assertEqual((total["paddy_qtl"], total["new_used_cmr"], total["old_used"]), (10.25, 7, 5))
		self.assertNotIn("new_unused", total)  # balance columns blank
		self.assertNotIn("oscsc_ob", total)

	def test_typed_values(self):
		mill = frappe.db.get_value("Mill Master", {"district": ["is", "set"]}, ["name", "district"], as_dict=True)
		if not mill:
			self.skipTest("Needs a Mill Master with a District")
		filters = frappe._dict(mill=mill.name, kms_year="_T-GSY", paddy_account=mill.district)
		set_value(mill.name, "_T-GSY", mill.district, "2025-01-15", "tr_receipt", 1500)
		set_value(mill.name, "_T-GSY", mill.district, "2025-01-01", "tr_receipt", 1600)  # same month: replaced
		set_value(mill.name, "_T-GSY", mill.district, "2025-01-01", "old_bag_rate", 15)
		entries = frappe.get_all(
			"Gunny Stock Yearly Entry", filters={"kms_year": "_T-GSY"}, fields=["report_column", "value"]
		)
		self.assertEqual(sorted((e.report_column, e.value) for e in entries), [("Actual Cost of Old Bags Procured", 15), ("Tr. Receipt", 1600)])
		set_value(mill.name, "_T-GSY", mill.district, "2025-01-01", "tr_receipt", 0)  # 0 removes it
		self.assertEqual(frappe.db.count("Gunny Stock Yearly Entry", {"kms_year": "_T-GSY"}), 1)
		self.assertRaises(frappe.ValidationError, set_value, mill.name, "_T-GSY", mill.district, "2025-01-01", "oscsc", 5)

	def test_oscsc_only_in_mill_district(self):
		mill = frappe.db.get_value("Mill Master", {"district": ["is", "set"]}, ["name", "district"], as_dict=True)
		other = frappe.db.get_value("District Master", {"name": ["!=", mill and mill.district]})
		if not (mill and other):
			self.skipTest("Needs a Mill Master with a District and another District")
		self.assertTrue(shows_oscsc(frappe._dict(mill=mill.name, paddy_account=mill.district)))
		self.assertFalse(shows_oscsc(frappe._dict(mill=mill.name, paddy_account=other)))

	def test_tr_issue_is_receipt_of_same_month_in_other_accounts(self):
		mill = frappe.db.get_value("Mill Master", {"district": ["is", "set"]}, ["name", "district"], as_dict=True)
		other = frappe.db.get_value("District Master", {"name": ["!=", mill and mill.district]})
		if not (mill and other):
			self.skipTest("Needs a Mill Master with a District and another District")
		set_value(mill.name, "_T-GSY1", mill.district, "2025-11-01", "tr_issue", 123959)
		# Other KMS Year, same District / same KMS Year, other District: receipt in Nov-25 (same month).
		for kms_year, district in (("_T-GSY2", mill.district), ("_T-GSY1", other)):
			filters = frappe._dict(mill=mill.name, kms_year=kms_year, paddy_account=district)
			self.assertEqual(transfer_receipts(filters, getdate("2026-01-31")), [(getdate("2025-11-01"), 123959)])
			self.assertEqual(transfer_receipts(filters, getdate("2025-11-30")), [(getdate("2025-11-01"), 123959)])
			self.assertEqual(transfer_receipts(filters, getdate("2025-10-31")), [])  # Nov not in the report
		# The account that issued them: no receipt.
		same = frappe._dict(mill=mill.name, kms_year="_T-GSY1", paddy_account=mill.district)
		self.assertEqual(transfer_receipts(same, getdate("2026-01-31")), [])
		rows = build_rows([getdate("2025-12-01")], {getdate("2025-12-01"): {"tr_receipt": 100, "tr_receipt_transfer": 123959}})
		self.assertEqual((rows[0]["tr_receipt"], rows[0]["tr_receipt_typed"], rows[0]["new_unused"]), (124059, 100, 124059))
