# Copyright (c) 2026, Profezzo and contributors

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

# Reports are built in the test itself: no test records needed for the linked doctypes.
IGNORE_TEST_RECORD_DEPENDENCIES = ["UOM", "User", "Miller Verification Report", "Mill Master", "Season Master"]

# Season Master records (made in setUpClass when missing).
KHARIF, RABI = "Kharif 2025", "Rabi 2025"

# Masked sample miller; quantities are the check values of the Annexure-1 sheet.
AGENCY = {
	"agency": "Sample Agency Ltd., District A",
	"season": KHARIF,
	"prog_paddy_received": 78534.020,
	"prog_paddy_milled": 44100.000,
	"verified_balance_paddy": 34434.020,
	"prog_rice_received": 29988.000,
	"prog_dc_fci": 17400,
	"prog_dc_rrc": 8370,
	"prog_delivered_fci": 15622.244,
	"prog_delivered_rrc": 6371.232,
	"verified_balance_rice": 7994.524,
}


def make_report(agencies=None, submit=False, **values):
	doc = frappe.get_doc(
		{
			"doctype": "Miller Verification Report",
			"miller_name": "Sample Rice Mill Pvt Ltd",
			"miller_code": "M999901",
			"kms": "2025-26",
			"variety": "Par-Boiled",
			"present_verification_date": "2026-09-02",
			"season": KHARIF,
			"meter_reading_last": 8788.65,
			"meter_reading_present": 8806.56,
			"meter_multiplier": 900,
			"certified_no_diversion": 1,
			"agencies": agencies if agencies is not None else [dict(AGENCY)],
			**values,
		}
	)
	# The sample miller is not in Mill Master (it needs a Company); seasons are checked in setUpClass.
	doc.flags.ignore_links = True
	if submit:
		doc.insert()
		doc.submit()
	else:
		doc.run_method("validate")
	return doc


# The next week's report of the same agency: only this week's figures are typed in.
NEXT_WEEK = {
	"agency": "Sample Agency Ltd., District A",
	"season": KHARIF,
	"prog_paddy_received": 80000,
	"paddy_milled_week": 1000,
	"rice_received_week": 680,
	"rice_delivered_week_fci": 500,
	"rice_delivered_week_rrc": 100,
	"prog_dc_fci": 17400,
	"prog_dc_rrc": 8370,
}


class TestMillerVerificationReport(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		for crop in ("Kharif", "Rabi"):
			if not frappe.db.exists("Season Master", f"{crop} 2025"):
				frappe.get_doc({"doctype": "Season Master", "crop_season": crop, "year": "2025"}).insert()

	def tearDown(self):
		frappe.db.rollback()

	def test_book_balance_paddy(self):
		row = make_report().agencies[0]
		self.assertEqual(row.book_balance_paddy, 34434.020)
		self.assertEqual(row.paddy_difference, 0)

	def test_book_balance_rice(self):
		row = make_report().agencies[0]
		self.assertEqual(row.prog_cmr_due, 29988.000)
		self.assertEqual(row.prog_delivered_total, 21993.476)
		self.assertEqual(row.book_balance_rice, 7994.524)
		self.assertEqual(row.rice_difference, 0)

	def test_dc_totals(self):
		self.assertEqual(make_report().agencies[0].prog_dc_total, 25770)

	def test_undelivered_totals(self):
		row = make_report().agencies[0]
		self.assertEqual(row.undelivered_fci, 1777.756)
		self.assertEqual(row.undelivered_rrc, 1998.768)
		self.assertEqual(row.undelivered_total, 3776.524)

	def test_parent_totals(self):
		second = {"agency": "Sample Agency Ltd., District B", "season": KHARIF, "prog_paddy_received": 15563.950}
		doc = make_report([dict(AGENCY), second])
		self.assertEqual(doc.total_prog_paddy_received, 94097.970)
		self.assertEqual(doc.total_book_balance_paddy, 49997.970)
		self.assertEqual(doc.total_prog_dc_total, 25770)
		self.assertEqual(doc.total_undelivered_total, 3776.524)
		self.assertEqual(doc.total_book_balance_rice, 7994.524)

	def test_units_consumed(self):
		# (8806.56 - 8788.65) x 900 = 16119 (the sheet shows 16120 rounded).
		self.assertEqual(make_report().total_units_consumed, 16119.0)
		self.assertEqual(make_report(meter_multiplier=None).total_units_consumed, 17.91)

	def test_present_reading_below_last(self):
		with self.assertRaises(frappe.ValidationError):
			make_report(meter_reading_present=8000)

	def test_negative_value_error(self):
		with self.assertRaises(frappe.ValidationError):
			make_report([dict(AGENCY, prog_paddy_milled=-5)])
		# Milled more than received: Book balance of paddy below 0.
		with self.assertRaises(frappe.ValidationError):
			make_report([dict(AGENCY, prog_paddy_milled=80000)])
		with self.assertRaises(frappe.ValidationError):
			make_report(contract_load=-1)

	def test_verified_balances_follow_book_balances(self):
		row = make_report([dict(AGENCY, verified_balance_paddy=1, verified_balance_rice=1)]).agencies[0]
		self.assertEqual(row.verified_balance_paddy, row.book_balance_paddy)
		self.assertEqual(row.verified_balance_rice, row.book_balance_rice)

	def test_first_report_keeps_opening_progressive_figures(self):
		row = make_report().agencies[0]
		self.assertEqual((row.prog_paddy_milled, row.prog_rice_received), (44100, 29988))
		self.assertEqual((row.prog_delivered_fci, row.prog_delivered_rrc), (15622.244, 6371.232))

	def test_progressive_from_previous_report(self):
		first = make_report(submit=True)
		second = make_report([dict(NEXT_WEEK)], present_verification_date="2026-09-09")
		row = second.agencies[0]
		self.assertEqual(row.prog_paddy_milled, 45100)  # 44100 + 1000
		self.assertEqual(row.book_balance_paddy, 34900)  # 80000 - 45100
		self.assertEqual(row.verified_balance_paddy, 34900)
		self.assertEqual(row.prog_rice_received, 30668)  # 29988 + 680
		self.assertEqual(row.prog_cmr_due, 30668)
		self.assertEqual(row.prog_delivered_fci, 16122.244)  # 15622.244 + 500
		self.assertEqual(row.prog_delivered_rrc, 6471.232)  # 6371.232 + 100
		self.assertEqual(row.undelivered_fci, 1277.756)  # 17400 - 16122.244
		self.assertEqual(row.undelivered_rrc, 1898.768)  # 8370 - 6471.232
		self.assertEqual(row.book_balance_rice, 8074.524)  # 30668 - 22593.476
		self.assertEqual(row.verified_balance_rice, 8074.524)
		# Another miller or KMS does not carry on from it.
		other = make_report([dict(NEXT_WEEK, prog_paddy_milled=5)], kms="2024-25").agencies[0]
		self.assertEqual(other.prog_paddy_milled, 5)
		self.assertTrue(first.name)

	def test_rice_received_from_fci_rice_percent(self):
		percent = frappe.db.get_value("Rice Delivery Setup", "Boiled", "cmr_percentage")
		if percent is None:
			frappe.get_doc({"doctype": "Rice Delivery Setup", "rice_type": "Boiled", "cmr_percentage": 68}).insert()
			percent = 68
		row = make_report([dict(AGENCY, paddy_milled_week=2600)]).agencies[0]
		self.assertEqual(row.rice_received_week, round(2600 * percent / 100, 3))
		# Typed in by hand: kept.
		row = make_report([dict(AGENCY, paddy_milled_week=2600, rice_received_week=1768)]).agencies[0]
		self.assertEqual(row.rice_received_week, 1768)
		# Raw mill: typed in.
		row = make_report([dict(AGENCY, paddy_milled_week=2600)], variety="Raw").agencies[0]
		self.assertFalse(row.rice_received_week)

	def test_dc_issued_from_dc_lots(self):
		frappe.db.set_single_value("Rice Lot Quantity", "lot_quantity", 290)
		lots = {"M999901": {"fci_issue": 60, "rrc_issue": 30}}
		with patch("ivri_od.procurement.report.dc_details.dc_details._dc_lots", return_value=lots):
			second_kharif = dict(AGENCY, agency="Sample Agency Ltd., District B")
			doc = make_report([dict(AGENCY), second_kharif])
		self.assertEqual((doc.agencies[0].prog_dc_fci, doc.agencies[0].prog_dc_rrc), (17400, 8700))  # 60 / 30 lots x 290
		# Only the first row of the season gets the DCs; the next keeps what was typed.
		self.assertEqual((doc.agencies[1].prog_dc_fci, doc.agencies[1].prog_dc_rrc), (17400, 8370))

	def test_paddy_received_from_target_allocation(self):
		# Two PPCs allotted to the sample mill for Kharif; Rabi has none (II stays as typed).
		for qty in (50000, 28534.02):
			frappe.get_doc(
				{"doctype": "Target Allocation", "season": KHARIF, "mill_name": "M999901",
				 "ppc_name": "Sample PPC", "target_quantity": qty}
			).db_insert()
		second = dict(AGENCY, agency="Sample Agency Ltd., District B", prog_paddy_received=0, prog_paddy_milled=0)
		doc = make_report([dict(AGENCY, prog_paddy_received=1), second])
		self.assertEqual(doc.agencies[0].prog_paddy_received, 78534.02)  # 50000 + 28534.02
		self.assertEqual(doc.agencies[0].book_balance_paddy, 34434.02)  # 78534.02 - 44100
		# Only the first agency gets it, so the mill's paddy is not counted twice.
		self.assertEqual(doc.agencies[1].prog_paddy_received, 0)
		self.assertEqual(doc.total_prog_paddy_received, 78534.02)
		# A season without Target Allocation: II stays as typed.
		rabi = make_report([dict(AGENCY, season=RABI, prog_paddy_received=15563.95, prog_paddy_milled=5000)], season=RABI)
		self.assertEqual(rabi.agencies[0].prog_paddy_received, 15563.95)

	def test_first_report_starts_from_zero(self):
		week = {"agency": "Sample Agency Ltd., District A", "season": KHARIF, "prog_paddy_received": 78534.02,
		        "paddy_milled_week": 1000, "rice_received_week": 680, "rice_delivered_week_fci": 400, "rice_delivered_week_rrc": 200,
		        "prog_dc_fci": 17400, "prog_dc_rrc": 8370}
		row = make_report([week]).agencies[0]
		self.assertEqual((row.prog_paddy_milled, row.prog_rice_received), (1000, 680))
		self.assertEqual((row.prog_delivered_fci, row.prog_delivered_rrc), (400, 200))
		self.assertEqual(row.book_balance_rice, 80)  # 680 - 600

	def test_new_report_filled_from_last_report(self):
		from ivri_od.procurement.doctype.miller_verification_report.miller_verification_report import get_last_report

		self.assertEqual(get_last_report("M999901", KHARIF), {"kms": "2025-26"})  # none yet: only the KMS
		make_report(submit=True, season=KHARIF, address="Sample Address", milling_capacity=24, contract_load=500)
		last = get_last_report("M999901", KHARIF)
		self.assertEqual(last["last_verification_date"], frappe.utils.getdate("2026-09-02"))  # its present date
		self.assertEqual(last["meter_reading_last"], 8806.56)  # its present reading
		self.assertEqual((last["address"], last["milling_capacity"], last["contract_load"]), ("Sample Address", 24, 500))
		self.assertEqual((last["kms"], last["variety"], last["meter_multiplier"]), ("2025-26", "Par-Boiled", 900))
		self.assertEqual([(r.agency, r.season) for r in last["agencies"]], [(AGENCY["agency"], KHARIF)])
		# Another season of the same mill has its own chain.
		self.assertEqual(get_last_report("M999901", RABI), {"kms": "2025-26"})

	def test_rows_and_kms_take_the_report_season(self):
		doc = make_report([dict(AGENCY, season=None), dict(AGENCY, agency="B", season=RABI)], season=KHARIF, kms=None)
		# A row without a season gets the report's; one given its own season keeps it.
		self.assertEqual([r.season for r in doc.agencies], [KHARIF, RABI])
		self.assertEqual(doc.kms, "2025-26")

	def test_agency_needed(self):
		with self.assertRaises(frappe.ValidationError):
			make_report([])
