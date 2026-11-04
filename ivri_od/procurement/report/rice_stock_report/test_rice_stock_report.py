# Copyright (c) 2026, Profezzo and contributors

import json
from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ivri_od.procurement.report.rice_stock_report.rice_stock_report import execute, fci_delivery, rrc_delivery

MILL = "_TEST_RICE_MILL"
FILTERS = {"mill": MILL, "kms_year": "25-26", "from_month": "2026-05-01", "to_month": "2026-07-31"}
# Paddy Stock Register's Issue for Milling (paddy, Qtl) by District: (date, district, qty).
ISSUE_FOR_MILLING = [
	(date(2026, 4, 20), "Balangir", 1000),  # before From Month: OB (1000 x 68% = 680)
	(date(2026, 5, 5), "Balangir", 5200),
	(date(2026, 5, 5), "Koraput", 800),  # every district counted: (5200 + 800) x 68% = 4080
	(date(2026, 8, 1), "Balangir", 9999),  # after To Month: not counted
]


def fake_issue_for_milling(filters, to_date):
	"""Stands in for the Paddy Stock Register: only the District's rows when one is given."""
	return [
		(day, "issue_for_milling", qty)
		for day, district, qty in ISSUE_FOR_MILLING
		if (not filters.paddy_account or district == filters.paddy_account) and day <= to_date
	]


def fci_row(sl, accepted_date, net_weight, depot_code="DW051602", depot_name="SWC KANTABHANJI", kms="2025-26", dc=""):
	return {
		"Sl#": sl,
		"DC Order No": dc,
		"KMS Year": kms,
		"Depot Code": depot_code,
		"Depot Name": depot_name,
		"Pending At": "Approved",
		"Net Weight": net_weight,
		"Weight After Moisture Cut": net_weight,
		"Accepted Date": accepted_date,
	}


def rrc_row(lot, receipt_date, qty, depot="DG051601-RMC,Kantabanji", status="Accepted", kms="2025-2026", dc="", district=""):
	return {"District": district, "KMS Year": kms, "DC No.": dc, "Lot No.": lot, "Receipt Date": receipt_date, "Depot": depot, "Qty(In Qtl.)": qty, "Challan Status": status}


class TestRiceStockReport(IntegrationTestCase):
	def setUp(self):
		if not frappe.db.exists("Mill Master", MILL):
			mill = frappe.get_doc({"doctype": "Mill Master", "miller_code": MILL, "type": "BOILED"})
			mill.insert(ignore_mandatory=True)  # no Company needed here
		frappe.db.set_value("Mill Master", MILL, "type", "BOILED")
		for rice_type, percentage in (("Boiled", 68), ("Raw", 67)):
			if not frappe.db.exists("Rice Delivery Setup", rice_type):
				frappe.get_doc({"doctype": "Rice Delivery Setup", "rice_type": rice_type, "cmr_percentage": percentage}).insert()
			frappe.db.set_value("Rice Delivery Setup", rice_type, "cmr_percentage", percentage)

		issue_patch = patch(
			"ivri_od.procurement.report.rice_stock_report.rice_stock_report.get_issue_for_milling",
			side_effect=fake_issue_for_milling,
		)
		issue_patch.start()
		self.addCleanup(issue_patch.stop)
		self.add("DCRO", "DC Transit Challan", [
			fci_row("1", "11-05-2026", "287.41811", dc="DCF-B1"),
			fci_row("2", "12-06-2026", "287.50925", depot_code="DW050101", depot_name="SWC BOLANGIR", dc="DCF-K1"),
			fci_row("3", "", "287.50000"),  # no AC Note yet: no Accepted Date, not counted
			fci_row("4", "13-05-2026", "287.5", kms="2024-25"),  # another KMS Year
		])
		self.add("SCMS", "Lot Search", [
			rrc_row("1", "14/04/2026", "100", dc="DCR-B1"),  # before From Month: OB
			rrc_row("2", "14/07/2026", "289.536", depot="DC050201-Madhiapali, Bolangir", dc="DCR-K1"),
			rrc_row("3", "20/07/2026", "289.74", dc="dcr-b1 "),  # case and spaces differ
			rrc_row("4", "21/07/2026", "289.74", status="Rejected"),
		])

	def tearDown(self):
		frappe.db.rollback()

	def add(self, site, section, rows):
		for i, cells in enumerate(rows, 1):
			frappe.get_doc(
				{
					"doctype": "Portal Record",
					"site": site,
					"section": section,
					"mill_id": MILL,
					"row_no": i,
					"record_key": f"{section}-{frappe.generate_hash(length=8)}",
					"row_data": json.dumps(cells),
				}
			).insert(ignore_permissions=True)

	def test_depot_columns_and_months(self):
		columns, data, message = execute(dict(FILTERS))
		labels = [c["label"] for c in columns]
		self.assertEqual(
			labels,
			[
				"Month", "OB", "Rice Received from Milling", "Total",
				"FCI: DW050101-SWC BOLANGIR", "FCI: DW051602-SWC KANTABHANJI", "FCI Total",
				"RRC: DC050201-Madhiapali, Bolangir", "RRC: DG051601-RMC,Kantabanji", "RRC Total",
				"Total Delivery", "CB",
			],
		)
		self.assertIn("1 DC Transit Challan rows are not counted", message)
		label = {c["fieldname"]: c["label"] for c in columns}
		by_month = {row["month"]: {label[k]: v for k, v in row.items() if k in label} for row in data}

		may, jun, jul, total = by_month["May-26"], by_month["Jun-26"], by_month["Jul-26"], by_month["Total"]
		# OB: 680 rice (April issue for milling) - 100 delivered to RRC in April.
		self.assertEqual(may["OB"], 580)
		self.assertEqual((may["Rice Received from Milling"], may["Total"]), (4080, 4660))
		self.assertEqual((may["FCI: DW051602-SWC KANTABHANJI"], may["FCI Total"], may["RRC Total"]), (287.42, 287.42, 0))
		self.assertEqual((may["Total Delivery"], may["CB"]), (287.42, 4372.58))
		self.assertEqual((jun["OB"], jun["FCI: DW050101-SWC BOLANGIR"], jun["CB"]), (4372.58, 287.51, 4085.07))
		self.assertEqual(
			(jul["RRC: DC050201-Madhiapali, Bolangir"], jul["RRC: DG051601-RMC,Kantabanji"], jul["RRC Total"]),
			(289.54, 289.74, 579.28),
		)
		self.assertEqual(jul["CB"], 3505.79)
		# Total row: OB of the first month, sums of the period, CB of the last month.
		self.assertEqual((total["OB"], total["Rice Received from Milling"], total["Total"]), (580, 4080, 4660))
		self.assertEqual((total["FCI Total"], total["RRC Total"], total["Total Delivery"]), (574.93, 579.28, 1154.21))
		self.assertEqual(total["CB"], 3505.79)

	def test_district_filter_uses_view_dc_numbers(self):
		for district in ("Balangir", "Koraput"):
			if not frappe.db.exists("District Master", district):
				frappe.get_doc({"doctype": "District Master", "district_name": district}).insert()
		frappe.db.set_value("Mill Master", MILL, "district", "Balangir")
		self.add("DCRO", "View DC", [
			{"District": "Balangir", "DC Code(RRC)": "DCF-B1"},
			{"District": "Balangir", "DC Code(RRC)": "DCR-B1"},
			{"District": "Koraput", "DC Code(RRC)": "DCF-K1"},
			{"District": "Koraput", "DC Code(RRC)": "DCR-K1"},
			{"District": "No District Matched", "DC Code(RRC)": "DCR-X1"},
		])
		columns, data, message = execute({**FILTERS, "district": "Balangir"})
		label = {c["fieldname"]: c["label"] for c in columns}
		by_month = {row["month"]: {label[k]: v for k, v in row.items() if k in label} for row in data}
		may, jun, jul, total = by_month["May-26"], by_month["Jun-26"], by_month["Jul-26"], by_month["Total"]
		# OB: 680 (April issue for milling of Balangir) - 100 (RRC lot of DCR-B1 in April).
		self.assertEqual(may["OB"], 580)
		self.assertEqual(may["Rice Received from Milling"], 3536)  # 5200 x 68%; Koraput's 800 left out
		self.assertEqual(may["FCI Total"], 287.42)  # DCF-B1
		self.assertEqual(jun["FCI Total"], 0)  # DCF-K1 is Koraput
		self.assertEqual(jul["RRC Total"], 289.74)  # DCR-B1 only
		self.assertEqual(total["CB"], round(580 + 3536 - 287.42 - 289.74, 2))
		self.assertIn("1 DCs of mill", message)

		# Lot Search's own District counts first, even when its DC has no District in View DC.
		self.add("SCMS", "Lot Search", [
			rrc_row("5", "22/07/2026", "100", depot="DC050201-Madhiapali, Bolangir", dc="DCR-X1", district="BALANGIR "),
			rrc_row("6", "23/07/2026", "50", dc="DCR-B1", district="KORAPUT"),  # its own District wins
		])
		columns, data, _message = execute({**FILTERS, "district": "Balangir"})
		label = {c["fieldname"]: c["label"] for c in columns}
		jul = {label[k]: v for k, v in data[2].items() if k in label}
		self.assertEqual((jul["RRC: DC050201-Madhiapali, Bolangir"], jul["RRC Total"]), (100, 389.74))

		# Every depot keeps its column, also when the District leaves it at 0.
		self.assertEqual(total["RRC: DC050201-Madhiapali, Bolangir"], 0)
		self.assertEqual(total["FCI: DW050101-SWC BOLANGIR"], 0)

		# Koraput: its own issue for milling, its own DCs.
		_columns, data, _message = execute({**FILTERS, "district": "Koraput"})
		self.assertEqual(data[0]["ob"], 0)
		self.assertEqual(data[0]["rice_received"], 544)  # 800 x 68%
		# July RRC: DCR-K1 289.54 + lot 6 (Lot Search District KORAPUT) 50.
		self.assertEqual((data[1]["fci_total"], data[2]["rrc_total"]), (287.51, 339.54))

	def test_raw_mill_uses_raw_percentage(self):
		frappe.db.set_value("Mill Master", MILL, "type", "RAW")
		_columns, data, _message = execute(dict(FILTERS))
		self.assertEqual(data[0]["ob"], round(1000 * 0.67 - 100, 2))
		self.assertEqual(data[0]["rice_received"], 4020)  # 6000 x 67%

	def test_mill_without_type(self):
		frappe.db.set_value("Mill Master", MILL, "type", "")
		self.assertRaises(frappe.ValidationError, execute, dict(FILTERS))

	def test_row_readers(self):
		self.assertEqual(fci_delivery(fci_row("1", "11-05-2026", "287.41811"))[1:], ("DW051602-SWC KANTABHANJI", 287.41811))
		self.assertIsNone(fci_delivery(fci_row("1", "", "287.5"))[0])
		self.assertEqual(str(rrc_delivery(rrc_row("1", "14/07/2026", "289.536"))[0]), "2026-07-14")
