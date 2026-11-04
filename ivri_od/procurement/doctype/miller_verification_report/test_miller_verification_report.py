# Copyright (c) 2026, Profezzo and contributors

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from ivri_od.procurement.doctype.miller_verification_report import miller_verification_report as mvr

# Reports are built in the test itself: no test records needed for the linked doctypes.
IGNORE_TEST_RECORD_DEPENDENCIES = ["UOM", "User", "Miller Verification Report", "Mill Master", "Season Master"]

# Masked sample miller; its District in Mill Master is Balangir.
MILL = "M999901"
PRESENT = "2026-09-02"  # no earlier report: the period is everything up to the day before


def make_report(columns=None, submit=False, **values):
	doc = frappe.get_doc(
		{
			"doctype": "Miller Verification Report",
			"miller_name": "Sample Rice Mill Pvt Ltd",
			"miller_code": MILL,
			"kms": "2025-26",
			"present_verification_date": PRESENT,
			"meter_reading_last": 8788.65,
			"meter_reading_present": 8806.56,
			"meter_multiplier": 900,
			"certified_no_diversion": 1,
			"agencies": columns if columns is not None else [{"district": "Balangir", "season": "Kharif"}],
			**values,
		}
	)
	doc.flags.ignore_links = True
	if submit:
		doc.insert()
		doc.submit()
	else:
		doc.run_method("validate")
	return doc


def view_dc(dc_no, district, lots, date="10-08-2026", season="KHARIF"):
	cells = {"District": district, "KMS (Year)": "2025-26", "Season": season, "DC Code(RRC)": dc_no, "Generated Date": date}
	return cells, [{"DC Type": "FCI" if dc_no.startswith("DCF") else "RRC", "Lots": str(lots)}]


# Transit Passes (Stock Account for Paddy's reader is mocked): {(District, Season Master): [(date, Qtls)]}.
PASSES = {
	("Balangir", "Kharif 2025"): [("2026-08-01", 2000), ("2026-08-30", 300), ("2026-09-05", 999)],
	("Koraput", "Kharif 2025"): [("2026-08-02", 450)],
}


def fake_transit_passes(filters, seasons, to_date):
	passes = [
		frappe._dict(name=f"TP-{i}", transit_pass_date=getdate(day), quantity=qty)
		for season in seasons
		for i, (day, qty) in enumerate(PASSES.get((filters.paddy_account, season), []))
		if getdate(day) <= getdate(to_date)
	]
	return passes, [frappe._dict(name="TP-NO-PPC")]


class TestMillerVerificationReport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for crop in ("Kharif", "Rabi"):
			if not frappe.db.exists("Season Master", f"{crop} 2025"):
				frappe.get_doc({"doctype": "Season Master", "crop_season": crop, "year": "2025"}).insert()

	def setUp(self):
		for district in ("Balangir", "Koraput"):
			if not frappe.db.exists("District Master", district):
				frappe.get_doc({"doctype": "District Master", "district_name": district}).insert()
		if not frappe.db.exists("Mill Master", MILL):
			mill = frappe.get_doc({"doctype": "Mill Master", "miller_code": MILL, "type": "BOILED"})
			mill.insert(ignore_mandatory=True)  # no Company needed here
		frappe.db.set_value("Mill Master", MILL, {"type": "BOILED", "district": "Balangir"})
		if not frappe.db.exists("Rice Delivery Setup", "Boiled"):
			frappe.get_doc({"doctype": "Rice Delivery Setup", "rice_type": "Boiled", "cmr_percentage": 68}).insert()
		frappe.db.set_value("Rice Delivery Setup", "Boiled", "cmr_percentage", 68)
		frappe.db.set_single_value("Rice Lot Quantity", "lot_quantity", 290)

		self.add("DCRO", "View DC", [
			view_dc("DCF-1", "Balangir", 2),
			view_dc("DCR-1", "Balangir", 3),
			view_dc("DCR-2", "Koraput", 1),
			view_dc("DCR-3", "No District Matched", 1),
			view_dc("DCF-9", "Balangir", 5, date="05-09-2026"),  # after the Present Verification Date
		])
		self.add("DCRO", "DC Transit Challan", [
			{"KMS Year": "2025-26", "DC Order No": "DCF-1", "Pending At": "Approved", "Accepted Date": "15-08-2026", "Net Weight": "287.4", "Weight After Moisture Cut": "287.4"},
			{"KMS Year": "2025-26", "DC Order No": "DCF-1", "Pending At": "Approved", "Accepted Date": "01-09-2026", "Net Weight": "287.5", "Weight After Moisture Cut": "287.5"},
			{"KMS Year": "2025-26", "DC Order No": "DCF-1", "Pending At": "Approved", "Accepted Date": "", "Net Weight": "287.5", "Weight After Moisture Cut": "287.5"},
		])
		self.add("SCMS", "Lot Search", [
			{"District": "BALANGIR", "KMS Year": "2025-2026", "DC No.": "DCR-1", "Receipt Date": "31/08/2026", "Qty(In Qtl.)": "289.5", "Challan Status": "Accepted"},
			# Its DC has no District in View DC: the Lot Search page's District counts.
			{"District": "BALANGIR", "KMS Year": "2025-2026", "DC No.": "DCR-3", "Receipt Date": "20/08/2026", "Qty(In Qtl.)": "289", "Challan Status": "Accepted"},
			{"District": "KORAPUT", "KMS Year": "2025-2026", "DC No.": "DCR-2", "Receipt Date": "01/09/2026", "Qty(In Qtl.)": "289", "Challan Status": "Accepted"},
			{"District": "BALANGIR", "KMS Year": "2025-2026", "DC No.": "DCR-9", "Receipt Date": "01/09/2026", "Qty(In Qtl.)": "289", "Challan Status": "Accepted"},
			{"District": "BALANGIR", "KMS Year": "2025-2026", "DC No.": "DCR-1", "Receipt Date": "01/09/2026", "Qty(In Qtl.)": "289", "Challan Status": "Rejected"},
		])
		patcher = patch.object(mvr, "get_transit_passes", side_effect=fake_transit_passes)
		patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.db.rollback()

	def add(self, site, section, rows):
		for i, row in enumerate(rows, 1):
			cells, details = row if isinstance(row, tuple) else (row, [])
			frappe.get_doc(
				{
					"doctype": "Portal Record",
					"site": site,
					"section": section,
					"mill_id": MILL,
					"row_no": i,
					"record_key": f"{section}-{frappe.generate_hash(length=8)}",
					"row_data": json.dumps(cells),
					"details": [{"line_no": n, "detail_data": json.dumps(d)} for n, d in enumerate(details, 1)],
					"detail_count": len(details),
				}
			).insert(ignore_permissions=True)

	def test_figures_from_portal_data(self):
		doc = make_report([{"district": "Balangir", "season": "Kharif", "paddy_milled_week": 500},
			{"district": "Koraput", "season": "Kharif"}, {"district": "Balangir", "season": "Rabi", "paddy_milled_week": 700}])
		balangir, koraput, rabi = doc.agencies
		self.assertEqual(balangir.agency, "Balangir")  # the column heading
		self.assertEqual(doc.variety, "Par-Boiled")  # from the mill's Type
		# I / II: Transit Passes up to the Present date; no earlier report, so the period is all of them.
		self.assertEqual((balangir.paddy_received_week, balangir.prog_paddy_received), (2300, 2300))
		# V typed; VI = V with no earlier report.
		self.assertEqual((balangir.paddy_milled_week, balangir.prog_paddy_milled), (500, 500))
		self.assertEqual((koraput.paddy_milled_week, koraput.prog_paddy_milled), (0, 0))
		self.assertEqual((rabi.paddy_milled_week, rabi.prog_paddy_milled), (700, 700))
		self.assertEqual(balangir.book_balance_paddy, 1800)  # 2300 - 500
		self.assertEqual(balangir.verified_balance_paddy, 1800)
		# IX: 68 % of V; X = IX with no earlier report.
		self.assertEqual((balangir.rice_received_week, balangir.prog_rice_received), (340, 340))
		# XII: lots x 290 of the District's DCs up to the Present date (DCR-3 by its Lot Search District).
		self.assertEqual((balangir.prog_dc_fci, balangir.prog_dc_rrc), (580, 1160))
		self.assertEqual(koraput.prog_dc_rrc, 290)
		# XI / XIII: FCI by Accepted Date; RRC by Receipt Date (DCR-3 by the Lot Search District).
		self.assertEqual((balangir.rice_delivered_week_fci, balangir.prog_delivered_fci), (574.9, 574.9))
		self.assertEqual((balangir.rice_delivered_week_rrc, balangir.prog_delivered_rrc), (578.5, 578.5))
		self.assertEqual(balangir.rice_delivered_week_total, round(574.9 + 578.5, 3))
		self.assertEqual((koraput.rice_delivered_week_rrc, koraput.prog_delivered_rrc), (289, 289))
		self.assertEqual(balangir.undelivered_total, round(580 + 1160 - 574.9 - 578.5, 3))
		self.assertEqual(balangir.book_balance_rice, round(340 - 574.9 - 578.5, 3))
		self.assertEqual(doc.total_prog_paddy_milled, 1200)

	def test_notes_for_rows_not_counted(self):
		result = mvr.get_figures(MILL, "2025-26", PRESENT, columns=[{"district": "Balangir", "season": "Kharif"}])
		notes = " ".join(result["notes"])
		self.assertNotIn("have no District in View DC", notes)  # DCR-3 takes its Lot Search District
		self.assertIn("1 Lot Search rows are not counted", notes)  # DCR-9 is not in View DC
		self.assertIn("1 DC Transit Challan rows are not counted: they have no Accepted Date", notes)
		self.assertIn("1 Transit Passes are not counted", notes)
		self.assertIsNone(result["last_verification_date"])

	def test_week_after_last_report(self):
		make_report(
			[{"district": "Balangir", "season": "Kharif", "paddy_milled_week": 1000}],
			submit=True,
			present_verification_date="2026-08-29",
		)
		doc = make_report([{"district": "Balangir", "season": "Kharif", "paddy_milled_week": 500},
			{"district": "Koraput", "season": "Kharif", "paddy_milled_week": 100}])
		self.assertEqual(doc.last_verification_date, getdate("2026-08-29"))
		row, koraput = doc.agencies
		self.assertEqual(row.paddy_received_week, 300)  # 30-08
		self.assertEqual((row.rice_delivered_week_fci, row.rice_delivered_week_rrc), (287.5, 289.5))  # 01-09, 31-08
		# VI / X: the last report's figures + this week's.
		self.assertEqual(row.prog_paddy_milled, 1500)  # 1000 + 500
		self.assertEqual(row.prog_rice_received, 1020)  # 680 + 340
		self.assertEqual((koraput.prog_paddy_milled, koraput.prog_rice_received), (100, 68))  # not in the last report

	def test_data_up_to_day_before_present_date(self):
		# 30-08: the Last Verification Date's own day is in this period; 01-09: the Present
		# Verification Date's own day is not (it is in the next report).
		make_report(
			[{"district": "Balangir", "season": "Kharif", "paddy_milled_week": 1000}],
			submit=True,
			present_verification_date="2026-08-30",
		)
		doc = make_report([{"district": "Balangir", "season": "Kharif"}], present_verification_date="2026-09-01")
		row = doc.agencies[0]
		self.assertEqual(row.paddy_received_week, 300)  # 30-08
		self.assertEqual(row.prog_paddy_received, 2300)  # 01-08 + 30-08
		self.assertEqual((row.rice_delivered_week_fci, row.rice_delivered_week_rrc), (0, 289.5))  # FCI 01-09 not yet; RRC 31-08
		self.assertEqual(mvr.data_up_to("2026-09-01"), getdate("2026-08-31"))

	def test_new_report_filled_from_last_report(self):
		self.assertEqual(mvr.get_last_report(MILL, "2025-26"), {})
		make_report(
			[{"district": "Balangir", "season": "Kharif"}, {"district": "Balangir", "season": "Rabi"}],
			submit=True,
			address="Sample Address",
			milling_capacity=24,
		)
		last = mvr.get_last_report(MILL, "2025-26")
		self.assertEqual(last["last_verification_date"], getdate(PRESENT))
		self.assertEqual(last["meter_reading_last"], 8806.56)
		self.assertEqual((last["address"], last["milling_capacity"]), ("Sample Address", 24))
		self.assertEqual([(r.district, r.season) for r in last["agencies"]], [("Balangir", "Kharif"), ("Balangir", "Rabi")])
		self.assertEqual(mvr.get_last_report(MILL, "2024-25"), {})  # another KMS Year

	def test_paddy_released(self):
		own, other = "Quantity of Paddy Released for Milling (Own District) (in Qtl)", "Quantity of Paddy Released for Milling (Other District)KORAPUT (in Qtl)"
		release = {"KMS Year": "2025-2026", "Season": "Kharif", "Status of Released Order": "Approved"}
		self.add("DCRO", "Paddy Release", [
			{**release, "Date of Requistion": "10-08-2026", own: "1000.00", other: "200.00"},
			{**release, "Date of Requistion": "30-08-2026", own: "500.00", other: "0.00"},
			{**release, "Date of Requistion": "05-09-2026", own: "999.00", other: "0.00"},  # after the Present Verification Date
			{**release, "Date of Requistion": "20-08-2026", own: "700.00", "Status of Released Order": "Rejected"},
			{**release, "Season": "Rabi", "Date of Requistion": "15-08-2026", own: "300.00"},
			{**release, "KMS Year": "2024-2025", "Date of Requistion": "15-08-2026", own: "400.00"},
		])
		doc = make_report([{"district": "Balangir", "season": "Kharif"}, {"district": "Koraput", "season": "Kharif"},
			{"district": "Balangir", "season": "Rabi"}], last_verification_date="2026-08-20")
		balangir, koraput, rabi = doc.agencies
		self.assertEqual((balangir.paddy_released_week, balangir.prog_paddy_released), (500, 1500))  # 30-08; 10-08 + 30-08
		self.assertEqual((koraput.paddy_released_week, koraput.prog_paddy_released), (0, 200))
		self.assertEqual((rabi.paddy_released_week, rabi.prog_paddy_released), (0, 300))
		self.assertEqual((doc.total_paddy_released_week, doc.total_prog_paddy_released), (500, 2000))
		self.assertIn({"district": "Balangir", "season": "Rabi"}, mvr.get_data_columns(MILL, "2025-26"))

	def test_data_columns(self):
		# View DC: Balangir and Koraput Kharif; DCR-3 has no District, its Lot Search row says BALANGIR.
		columns = [("Balangir", "Kharif"), ("Koraput", "Kharif")]
		self.assertEqual([(c["district"], c["season"]) for c in mvr.get_data_columns(MILL, "2025-26")], columns)
		self.add("DCRO", "View DC", [view_dc("DCF-R1", "BALANGIR", 1, season="RABI")])
		columns.insert(1, ("Balangir", "Rabi"))
		self.assertEqual([(c["district"], c["season"]) for c in mvr.get_data_columns(MILL, "2025-26")], columns)
		self.assertEqual(mvr.get_data_columns(MILL, "2024-25"), [])  # another KMS Year

	def test_column_checks(self):
		with self.assertRaises(frappe.ValidationError):
			make_report([])
		with self.assertRaises(frappe.ValidationError):  # the same District and Season twice
			make_report([{"district": "Balangir", "season": "Kharif"}, {"district": "Balangir", "season": "Kharif"}])
		with self.assertRaises(frappe.ValidationError):
			make_report(kms="2025")

	def test_frk_typed_and_not_negative(self):
		row = make_report([{"district": "Balangir", "season": "Kharif", "frk_percent": 1, "frk_qty": 10.2}]).agencies[0]
		self.assertEqual((row.frk_percent, row.frk_qty), (1, 10.2))
		with self.assertRaises(frappe.ValidationError):
			make_report([{"district": "Balangir", "season": "Kharif", "frk_qty": -1}])
		with self.assertRaises(frappe.ValidationError):
			make_report([{"district": "Balangir", "season": "Kharif", "paddy_milled_week": -1}])

	def test_units_consumed(self):
		# (8806.56 - 8788.65) x 900 = 16119 (the sheet shows 16120 rounded).
		self.assertEqual(make_report().total_units_consumed, 16119.0)
		self.assertEqual(make_report(meter_multiplier=None).total_units_consumed, 17.91)
		with self.assertRaises(frappe.ValidationError):
			make_report(meter_reading_present=8000)
		with self.assertRaises(frappe.ValidationError):
			make_report(contract_load=-1)
