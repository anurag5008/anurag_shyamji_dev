# Copyright (c) 2026, Profezzo and contributors

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import (
	build_rows,
	classify,
	dcro_kms_year,
	dcro_release,
	get_months,
	kms_year_label,
	season_code_from_pass_key,
	season_master_year,
	tp_receipts,
	validate_filters,
)

FROM_DATE = getdate("2025-11-01")


def tp(transit_pass_date, quantity):
	return frappe._dict(transit_pass_date=transit_pass_date, quantity=quantity)


# Transit passes: each counts its TP quantity in the month of its Transit Pass Date.
PASSES = [
	tp("2025-10-20", 60),  # October: before the period, goes to OB
	tp("2025-11-03", 50),
	tp("2025-11-05", 30),
	tp("2025-11-06", 30),
	tp("2025-11-20", 39.5),
	tp("2026-01-04", 0.5),
]

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
		movements = tp_receipts(PASSES)
		movements.append(dcro_release(DCRO_ROW, SKIP))
		movements.append((getdate("2025-10-25"), "issue_for_milling", 10))
		opening, by_month = classify(movements, FROM_DATE)
		return build_rows(get_months(FROM_DATE, getdate("2026-01-31")), opening, by_month)

	def test_pacs_is_tp_quantity_on_transit_pass_date(self):
		receipts = tp_receipts(PASSES + [tp(None, 99)])  # no date: not counted
		self.assertEqual(receipts[1], (getdate("2025-11-03"), "pacs", 50))
		self.assertEqual([qty for _date, _column, qty in receipts], [60, 50, 30, 30, 39.5, 0.5])

	def test_wshg_ppc_goes_to_wshgs(self):
		# A pass whose PPC is ticked Is WSHG in PPC Master: Receipts - WSHGs, not PACs, same month.
		wshg = frappe._dict(transit_pass_date="2025-11-10", quantity=25, is_wshg=1)
		receipts = tp_receipts(PASSES + [wshg])
		self.assertEqual(receipts[-1], (getdate("2025-11-10"), "wshgs", 25))
		opening, by_month = classify(receipts, FROM_DATE)
		november = build_rows(get_months(FROM_DATE, getdate("2025-11-30")), opening, by_month)[0]
		self.assertEqual((november["pacs"], november["wshgs"]), (149.5, 25))
		self.assertEqual(november["total_paddy"], round(november["ob"] + 149.5 + 25, 2))

	def test_dcro_release(self):
		self.assertEqual(dcro_release(DCRO_ROW, SKIP), (getdate("2025-11-15"), "issue_for_milling", 75.5))
		self.assertIsNone(dcro_release({**DCRO_ROW, "Status of Released Order": "Rejected"}, SKIP))
		self.assertIsNone(dcro_release({**DCRO_ROW, "Date of Requistion": ""}, SKIP))

	def test_dcro_release_of_one_district(self):
		row = {
			**DCRO_ROW,
			"Quantity of Paddy Released for Milling (Other District)KORAPUT (in Qtl)": "20.00",
			"Quantity of Paddy Released for Milling (Other District) (in Qtl) 2": "4.00",
		}
		districts = {"balangir": "Balangir", "koraput": "Koraput"}
		release = lambda district, own="Balangir": dcro_release(row, SKIP, district, own, districts)[2]
		self.assertEqual(release("Balangir"), 70)  # Own District of a Balangir mill
		self.assertEqual(release("Koraput"), 20)  # header word matched to District Master
		self.assertEqual(release("Koraput", own="Koraput"), 90)  # a Koraput mill's own + Koraput columns
		self.assertEqual(release("Balangir", own=None), 0)  # mill without District: own not counted
		self.assertEqual(dcro_release(row, SKIP)[2], 99.5)  # no district: every column

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

	def test_paddy_released_does_not_change_stock(self):
		movements = tp_receipts(PASSES) + [
			(getdate("2025-10-25"), "paddy_released", 40),  # before the period: not in OB
			(getdate("2025-11-15"), "paddy_released", 75.5),
			(getdate("2025-11-20"), "issue_for_milling", 30),
		]
		opening, by_month = classify(movements, FROM_DATE)
		rows = build_rows(get_months(FROM_DATE, getdate("2025-12-31")), opening, by_month)
		november, total_row = rows[0], rows[-1]
		self.assertEqual(november["ob"], 60)  # October receipt only
		self.assertEqual(november["paddy_released"], 75.5)
		self.assertEqual((november["issue_for_milling"], november["total"]), (30, 30))
		self.assertEqual(november["cb"], round(60 + 149.5 - 30, 2))
		self.assertEqual(total_row["paddy_released"], 75.5)

	def test_column_order(self):
		from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import get_columns

		fields = [c["fieldname"] for c in get_columns()]
		self.assertEqual(fields.index("paddy_released") + 1, fields.index("issue_for_milling"))

	def test_dcro_kms_year(self):
		for text in ("2024-2025", "2024-25", "24-25", " 2024 - 2025 "):
			self.assertEqual(dcro_kms_year(text), 2024)
		for text in ("", None, "2024", "Kharif"):
			self.assertIsNone(dcro_kms_year(text))

	def test_season_code_from_pass_key(self):
		self.assertEqual(season_code_from_pass_key("M051007-BAKTI(S1050104)-K25-TP45"), "K25")
		self.assertEqual(season_code_from_pass_key(""), "")

	def test_kms_years_of_mill(self):
		from ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy import mill_tp_years

		year_of = {"Kharif 2025": 2025, "Rabi 2025": 2025, "Kharif 2024": 2024}
		rows = [
			frappe._dict(season="Kharif(2025)", miller="MILL A(M1)", key_mill="M1", key_season="K25"),
			frappe._dict(season="", miller="", key_mill="M1", key_season="R25"),  # season from the key
			frappe._dict(season="Kharif(2024)", miller="MILL B(M2)", key_mill="M2", key_season="K24"),
		]
		with patch("frappe.db.sql", return_value=rows), patch(
			"ivri_od.procurement.report.stock_account_for_paddy.stock_account_for_paddy.resolve_season_master_name",
			side_effect=lambda text: {"Kharif(2025)": "Kharif 2025", "R25": "Rabi 2025", "Kharif(2024)": "Kharif 2024"}.get(text),
		):
			self.assertEqual(mill_tp_years("M1", year_of), {2025})  # no 24-25 for M1
			self.assertEqual(mill_tp_years("M2", year_of), {2024})
			self.assertEqual(mill_tp_years("M3", year_of), set())

	def test_kms_year(self):
		self.assertEqual(kms_year_label(2025), "25-26")
		self.assertEqual(kms_year_label(2099), "99-00")
		self.assertEqual(season_master_year("25-26"), "2025")
		for wrong in ("2025", "25-27", ""):
			self.assertRaises(frappe.ValidationError, season_master_year, wrong)

	def test_from_month_after_to_month(self):
		filters = frappe._dict(
			mill="MILL",
			kms_year="25-26",
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
