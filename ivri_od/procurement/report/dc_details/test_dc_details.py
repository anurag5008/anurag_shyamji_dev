# Copyright (c) 2026, Profezzo and contributors

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from ivri_od.procurement.report.dc_details.dc_details import _add_pending, _in_season, _line, _total

RAW = frappe._dict(rice_type="Raw", cmr_percentage=67, driage_percentage=0.078)
BOILED = frappe._dict(rice_type="Boiled", cmr_percentage=68, driage_percentage=0)


class TestDCDetails(IntegrationTestCase):
	def test_figures_as_in_dc_details_sheet(self):
		# Figures of the Kharif 25-26 DC Details sheet (SSPP BLD and SSPP RAW).
		boiled = _line(
			frappe._dict(name="M1", company="SSPP BLD", type="BOILED", lot_quantity=290),
			BOILED,
			78534.02,
			{"fci_issue": 90, "fci_delivery": 84, "rrc_issue": 40, "rrc_delivery": 39},
		)
		self.assertEqual(boiled["driage"], 0)
		self.assertEqual(boiled["cmr_due"], 53403.13)
		self.assertEqual(boiled["total_lot"], 184)
		self.assertEqual((boiled["fci_balance"], boiled["rrc_balance"]), (6, 1))
		self.assertEqual((boiled["total_delivery"], boiled["total_dc_issued"]), (123, 130))
		self.assertEqual((boiled["total_dc_issue_balance"], boiled["total_delivery_balance"]), (54, 61))
		self.assertEqual(boiled["vr_pending"], 0)
		self.assertEqual(boiled["delivery_percent"], 66.79)

		raw = _line(
			frappe._dict(name="M2", company="SSPP RAW", type="RAW", lot_quantity=290),
			RAW,
			58372.69,
			{"fci_issue": 42, "fci_delivery": 39},
		)
		self.assertEqual(raw["driage"], 45.53)
		self.assertEqual(raw["paddy_after_driage"], 58327.16)
		self.assertEqual(raw["cmr_due"], 39079.2)
		self.assertEqual(raw["total_lot"], 135)
		self.assertEqual(raw["delivery_percent"], 28.94)

		total = _total([boiled, raw])
		self.assertEqual(total["driage"], 45.53)
		self.assertEqual(total["total_lot"], 319)

	def test_no_setup_or_lot_quantity(self):
		line = _line(frappe._dict(name="M3", company="X", type="RAW", lot_quantity=0), None, 100, {})
		self.assertEqual((line["cmr_due"], line["total_lot"], line["delivery_percent"]), (0, 0, 0))

	def test_season_of_dc(self):
		kharif_2025 = frappe._dict(crop_season="Kharif", year="2025")
		self.assertTrue(_in_season({"kms_year": "2025-26", "season": "KHARIF"}, kharif_2025))
		self.assertTrue(_in_season({"kms_year": "2025-26", "season": ""}, kharif_2025))
		self.assertFalse(_in_season({"kms_year": "2025-26", "season": "RABI"}, kharif_2025))
		self.assertFalse(_in_season({"kms_year": "2024-25", "season": "KHARIF"}, kharif_2025))
		self.assertFalse(_in_season({"kms_year": "", "season": "KHARIF"}, kharif_2025))

	def test_pending_lots(self):
		def rows(*cells):
			return [frappe._dict(name=f"PR-{i}", row_data=json.dumps(c), mill_id="M051007") for i, c in enumerate(cells)]

		records = {
			("SCMS", "Lot Search"): rows({"DC No.": "DCR051808", "Lot No.": "39", "Challan Status": "Accepted"}),
			("SCMS", "Transit Challan RRC"): rows(
				{"DC No": "DCR051808", "Lot No": "39", "Lot Challan Receipt status": "Accepted"},  # received
				{"DC No": "DCR051808", "Lot No": "40", "Lot Challan Receipt status": "Accepted"},  # pending
				{"DC No": "DCR051808", "Lot No": "41", "Lot Challan Receipt status": "Rejected"},
			),
			("DCRO", "DC Transit Challan"): rows(
				{"DC Order No": "DCF050748", "Lot No.": "32", "Pending At": "Approved"},
				{"DC Order No": "DCF050748", "Lot No.": "33", "Pending At": "Assitant Depot"},
				{"DC Order No": "DCF050748", "Lot No.": "33", "Pending At": "Assitant Depot"},  # read twice
			),
		}
		dcs = {"DCR051808": {"dc_no": "DCR051808"}}
		with patch(
			"ivri_od.procurement.report.dc_details.dc_details._records",
			side_effect=lambda site, section: records[(site, section)],
		):
			_add_pending(dcs)
		self.assertEqual(dcs["DCR051808"]["pending"], {"40"})
		self.assertEqual(dcs["DCF050748"]["pending"], {"33"})
		self.assertEqual(dcs["DCF050748"]["dc_type"], "FCI")

	def test_pending_is_shown_only(self):
		mill = frappe._dict(name="M1", company="SSPP BLD", type="BOILED", lot_quantity=290)
		lots = {"fci_issue": 90, "fci_delivery": 84, "rrc_issue": 40, "rrc_delivery": 39}
		without = _line(mill, BOILED, 78534.02, lots)
		with_pending = _line(mill, BOILED, 78534.02, {**lots, "fci_pending": 2, "rrc_pending": 1})
		self.assertEqual((with_pending["fci_pending"], with_pending["rrc_pending"]), (2, 1))
		for field in ("fci_delivery", "fci_balance", "rrc_balance", "total_delivery", "total_delivery_balance", "delivery_percent"):
			self.assertEqual(with_pending[field], without[field])
