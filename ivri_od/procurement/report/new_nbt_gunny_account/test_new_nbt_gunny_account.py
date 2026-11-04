# Copyright (c) 2026, Profezzo and contributors

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.report.new_nbt_gunny_account.new_nbt_gunny_account import (
	build_rows,
	classify,
	district_label,
	get_columns,
	get_months,
	pp_movements,
	register_bags,
	set_pp_bags,
)

FROM_DATE = getdate("2025-11-01")
DISTRICTS = ["Balangir", "Kalahandi"]


# (date, column, District, bag type, bags) as get_movements gives them.
MOVEMENTS = [
	("2025-10-01", "receipts", "", "oscsc", 1000),  # before From Month: goes to OB
	("2025-10-10", "receipts", "", "pp", 300),
	("2025-10-15", "issue", "Balangir", "pp", 100),  # before From Month: out of OB
	("2025-11-03", "receipts", "", "oscsc", 500),
	("2025-11-04", "other", "", "oscsc", 20),
	("2025-11-10", "issue", "Balangir", "oscsc", 580),
	("2025-11-12", "issue", "Kalahandi", "oscsc", 580),
	("2025-12-05", "receipts", "", "pp", 80),
	("2026-01-02", "issue", "Kalahandi", "pp", 30),
]


class TestNewNBTGunnyAccount(IntegrationTestCase):
	def get_rows(self):
		opening, by_month = classify(MOVEMENTS, FROM_DATE)
		return build_rows(get_months(FROM_DATE, getdate("2026-01-31")), DISTRICTS, opening, by_month)

	def test_one_issue_column_per_district(self):
		columns = get_columns(DISTRICTS)
		self.assertEqual(len(columns), 1 + 2 * 8)  # Month + OSCSC / PP of 8 groups
		self.assertEqual(columns[9]["label"], "Issue Balangir - OSCSC")
		self.assertEqual(columns[11]["fieldname"], "issue_kalahandi_oscsc")
		self.assertEqual(len(get_columns([])), 1 + 2 * 6)

	def test_month_rows(self):
		rows = self.get_rows()
		self.assertEqual([row["month"] for row in rows], ["Nov-25", "Dec-25", "Jan-26", "TOTAL"])
		nov = rows[0]
		self.assertEqual(nov["ob_oscsc"], 1000)
		self.assertEqual(nov["ob_pp"], 200)
		self.assertEqual(nov["total_receipts_oscsc"], 1520)  # OB + Receipts + Other
		self.assertEqual((nov["issue_balangir_oscsc"], nov["issue_kalahandi_oscsc"]), (580, 580))
		self.assertEqual(nov["total_issue_oscsc"], 1160)  # all Districts
		self.assertEqual(nov["cb_oscsc"], 360)
		# OB of a month = CB of the month before.
		self.assertEqual(rows[1]["ob_oscsc"], 360)
		self.assertEqual(rows[1]["cb_pp"], 280)
		self.assertEqual(rows[2]["cb_pp"], 250)
		# For editing PP in the report.
		self.assertEqual(nov["month_date"], "2025-11-01")
		self.assertEqual(nov["pp_districts"]["issue_kalahandi_pp"], "Kalahandi")

	def test_total_row(self):
		total = self.get_rows()[-1]
		self.assertIsNone(total["ob_oscsc"])
		self.assertEqual(total["receipts_pp"], 80)
		self.assertEqual(total["total_receipts_oscsc"], 520)  # without OB
		self.assertEqual(total["total_issue_oscsc"], 1160)
		self.assertEqual((total["cb_oscsc"], total["cb_pp"]), (360, 250))  # CB of the last month

	def test_procured_district_without_delivery_is_zero(self):
		# Procured in Koraput (Transit Passes) but no rice delivered there yet: its column shows 0.
		opening, by_month = classify(MOVEMENTS, FROM_DATE)
		rows = build_rows(get_months(FROM_DATE, getdate("2026-01-31")), [*DISTRICTS, "Koraput"], opening, by_month)
		self.assertEqual([(row["issue_koraput_oscsc"], row["issue_koraput_pp"]) for row in rows], [(0, 0)] * 4)
		self.assertEqual(rows[0]["total_issue_oscsc"], 1160)
		self.assertEqual(rows[0]["pp_districts"]["issue_koraput_pp"], "Koraput")

	def test_register_receipts_and_other(self):
		cells = {
			"Date - A": "29/10/2026",
			"OB OF GUNNY (in Bags) - B": "10200",
			"RECEIPT OF GUNNY (in Bags) - ROAD - C": "78,500",
			"RECEIPT OF GUNNY (in Bags) - RAKE - D": "100",
			"RECEIPT OF GUNNY (in Bags) - CONCOR - E": "0",
			"RECEIPT OF GUNNY (in Bags) - TRANSFER (RECEIPT INTRA DIST) - F": "10000",
			"RECEIPT OF GUNNY (in Bags) - SPECIAL CASE STOCK TRANSFERD - J": "5",
			"TOTAL RECEIPT (in Bags) - K=(C+D+E+F+G+H+I+J)": "88605",
			"UTILIZATION (Issue) (in Bags) - OSCSC - M": "23780",
		}
		self.assertEqual(register_bags(cells), {"receipts": 78600, "other": 10005})

	def test_district_as_in_master(self):
		districts = {"balangir": "Balangir"}
		self.assertEqual(district_label("BALANGIR ", districts), "Balangir")
		self.assertEqual(district_label("Somewhere", districts), "Somewhere")
		self.assertEqual(district_label("", districts), "No District")

	def test_pp_bags_typed_in_report(self):
		mill = frappe.get_all("Mill Master", pluck="name", limit=1)
		district = frappe.get_all("District Master", pluck="name", limit=1)
		if not (mill and district):
			self.skipTest("Needs a Mill Master and a District Master")
		mill, district = mill[0], district[0]
		kms_year = "_T-NBT"
		self.assertEqual(set_pp_bags(mill, kms_year, "2025-11-15", "Receipts", bags=120), 120)
		self.assertEqual(set_pp_bags(mill, kms_year, "2025-11-01", "Receipts", bags=150), 150)  # same month: replaced
		set_pp_bags(mill, kms_year, "2025-12-01", "Issue", district, 40)
		movements = sorted(pp_movements(mill, kms_year, getdate("2025-12-31")))
		self.assertEqual(
			movements,
			[(getdate("2025-11-01"), "receipts", "", "pp", 150), (getdate("2025-12-01"), "issue", district, "pp", 40)],
		)
		# Empty removes the entry.
		set_pp_bags(mill, kms_year, "2025-11-01", "Receipts", bags=0)
		self.assertEqual(len(pp_movements(mill, kms_year, getdate("2025-12-31"))), 1)
		self.assertRaises(frappe.ValidationError, set_pp_bags, mill, kms_year, "2025-11-01", "Issue", "Nowhere", 5)
