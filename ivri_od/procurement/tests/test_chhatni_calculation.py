# Copyright (c) 2026, Profezzo and Contributors
# See license.txt
"""Chhatni calculation, ±0.3 percentage-point tolerance and Mandi Book chhatni columns.

Mocked tests: no site, no database.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement.grn_tp_fulfillment import (
	CHHATNI_NOT_RECEIVED,
	CHHATNI_PENDING,
	CHHATNI_RECEIVED,
	EXTRA_CHHATNI_RECEIVED,
	actual_chhatni_pct,
	actual_chhatni_status,
	calculate_chhatni_metrics,
	chhatni_from_rate,
	chhatni_pct_band,
	excess_after_chhatni_qt,
)

MANDI_BOOK = "ivri_od.procurement.report.mandi_book.mandi_book"


class _NoSiteMixin:
	def setUp(self):
		frappe.local.lang = "en"
		# flt(value, precision) reads the rounding method from System Settings; use Frappe's default.
		patcher = patch.object(frappe, "get_system_settings", MagicMock(return_value=None), create=True)
		patcher.start()
		self.addCleanup(patcher.stop)


class TestChhatniCalculation(_NoSiteMixin, unittest.TestCase):
	def test_example_280_qt_at_4_kg_per_qtl(self):
		# Received % on the Chhatni form = Chhatni QT ÷ TP Quantity × 100: 11.2 ÷ 250 = 4.48%.
		self.assertEqual(
			chhatni_from_rate(280, 4, 250), {"chhatni_kg": 1120.0, "chhatni_qt": 11.2, "received_chhatni_pct": 4.48}
		)
		self.assertEqual(chhatni_from_rate(280, 4, 280)["received_chhatni_pct"], 4.0)

	def test_zero_or_empty_tp_quantity_keeps_kg_and_qt(self):
		for tp_qty in (0, None, "", -1):
			self.assertEqual(
				chhatni_from_rate(280, 4, tp_qty), {"chhatni_kg": 1120.0, "chhatni_qt": 11.2, "received_chhatni_pct": 0.0}
			)

	def test_zero_missing_or_negative_net_weight(self):
		for net in (0, None, -10, "0"):
			self.assertEqual(
				chhatni_from_rate(net, 4, 250), {"chhatni_kg": 0.0, "chhatni_qt": 0.0, "received_chhatni_pct": 0.0}
			)
			self.assertEqual(actual_chhatni_pct(11.2, net), 0.0)

	def test_tolerance_boundaries_in_percentage_points(self):
		cases = {4.30: "within", 4.31: "above", 3.70: "within", 3.69: "below", 4.0: "within"}
		for actual, band in cases.items():
			self.assertEqual(chhatni_pct_band(actual, 4), band, actual)

	def test_tolerance_is_not_a_relative_multiplier(self):
		# A relative 0.3% of 4% would allow only 3.988% - 4.012%.
		self.assertEqual(chhatni_pct_band(4.2, 4), "within")
		self.assertEqual(chhatni_pct_band(3.8, 4), "within")

	def test_actual_status_mapping(self):
		self.assertEqual(actual_chhatni_status(250, 4.31, 4), EXTRA_CHHATNI_RECEIVED)
		self.assertEqual(actual_chhatni_status(250, 4.0, 4), CHHATNI_RECEIVED)
		self.assertEqual(actual_chhatni_status(250, 3.69, 4), CHHATNI_PENDING)
		self.assertEqual(actual_chhatni_status(250, 0, 4), CHHATNI_PENDING)  # no Chhatni record yet
		self.assertEqual(actual_chhatni_status(250, 4.0, 0), CHHATNI_PENDING)  # no assigned rate
		self.assertEqual(actual_chhatni_status(0, 4.0, 4), CHHATNI_NOT_RECEIVED)  # no TP quantity

	def test_excess_after_chhatni(self):
		self.assertEqual(excess_after_chhatni_qt(250, 280, 11.2), 18.8)
		self.assertEqual(excess_after_chhatni_qt(250, 255, 11.2), 0.0)  # negative shows 0
		self.assertEqual(excess_after_chhatni_qt(250, 280, 0), 30.0)  # no Chhatni record yet
		self.assertEqual(excess_after_chhatni_qt(250, 0, 0), 0.0)

	def test_grn_status_unchanged_by_shared_band(self):
		"""GRN keeps "Chhatni Not Received" below the band; only Mandi Book shows "Chhatni Pending"."""
		cases = {312: CHHATNI_RECEIVED, 312.9: CHHATNI_RECEIVED, 313: EXTRA_CHHATNI_RECEIVED, 310.9: CHHATNI_NOT_RECEIVED}
		for received, status in cases.items():
			self.assertEqual(calculate_chhatni_metrics(300, received, 4)["status"], status, received)


class TestMandiBookChhatni(_NoSiteMixin, unittest.TestCase):
	KEY_A = "M051007-AGALPUR(S1050118)-K25-TP28"
	KEY_B = "M051007-DUDUKA(S1050113)-K25-TP142"

	def _grn(self, key, net_weight, tp_quantity=250, chhatni=4, tp_no="28"):
		return frappe._dict(
			name=f"GRN-{key[-4:]}-{net_weight}",
			grn_no="",
			pass_unique_key=key,
			ppc="PPC",
			ppc_name="PPC",
			mill_name="Mill",
			cmr_season="Kharif 2025",
			transit_pass_no=tp_no,
			tp_quantity=tp_quantity,
			chhatni=chhatni,
			net_weight=net_weight,
			deduction=0,
			tp_fulfillment_status="",
		)

	def _run(self, grns, chhatni_rows):
		def get_all(doctype, **kwargs):
			return {"GRN Note": grns, "Chhatni": chhatni_rows}[doctype]

		patches = [
			patch.object(frappe, "get_all", side_effect=get_all, create=True),
			patch(f"{MANDI_BOOK}._weigh_bridges_for", return_value={}),
			patch(f"{MANDI_BOOK}._bags_by_wbm", return_value={}),
			patch(f"{MANDI_BOOK}._entries_for", return_value={}),
			patch(f"{MANDI_BOOK}._mill_companies", return_value={}),
			patch(f"{MANDI_BOOK}._mill_label", return_value=("Mill", "M051007")),
			patch(f"{MANDI_BOOK}._rst_lines", return_value=[]),
			patch(f"{MANDI_BOOK}.ppc_display_name", side_effect=lambda value: value),
		]
		for patcher in patches:
			patcher.start()
			self.addCleanup(patcher.stop)
		from ivri_od.procurement.report.mandi_book.mandi_book import execute

		columns, data = execute({})
		return columns, {row["pass_unique_key"]: row for row in data}

	def _chhatni(self, name, key, chhatni_qt, received_pct):
		"""Saved Chhatni record; received_pct = Chhatni QT ÷ TP Quantity × 100 as stored on it."""
		return frappe._dict(name=name, pass_unique_key=key, chhatni_qt=chhatni_qt, received_chhatni_pct=received_pct)

	def test_example_pass_with_chhatni_record(self):
		# 280 QT × 4 kg/Qtl = 11.2 QT; 11.2 ÷ TP 250 = 4.48%, above 4% + 0.3.
		_, rows = self._run(
			[self._grn(self.KEY_A, 140), self._grn(self.KEY_A, 140)],
			[self._chhatni("CH-1", self.KEY_A, 11.2, 4.48)],
		)
		row = rows[self.KEY_A]
		self.assertEqual(row["total_received"], 280.0)
		self.assertEqual(row["excess_received_qty"], 18.8)
		self.assertEqual(row["actual_chhatni_pct"], 4.48)
		self.assertEqual(row["chhatni_status"], EXTRA_CHHATNI_RECEIVED)
		self.assertEqual(row["chhatni_received_qty"], 11.2)

	def test_received_pct_is_saved_value_not_the_rate(self):
		"""Bug: the column showed Chhatni (Kg per Qtl) (4) instead of the record's Received Chhatni %."""
		_, rows = self._run([self._grn(self.KEY_A, 280, chhatni=4)], [self._chhatni("CH-1", self.KEY_A, 11.2, 4.48)])
		self.assertEqual(rows[self.KEY_A]["chhatni_assigned"], 4.0)
		self.assertEqual(rows[self.KEY_A]["actual_chhatni_pct"], 4.48)

	def test_each_pass_gets_only_its_own_chhatni(self):
		_, rows = self._run(
			[self._grn(self.KEY_A, 280), self._grn(self.KEY_B, 260, tp_no="142")],
			[self._chhatni("CH-1", self.KEY_A, 10.0, 4.0), self._chhatni("CH-2", self.KEY_B, 13.0, 5.2)],
		)
		self.assertEqual((rows[self.KEY_A]["actual_chhatni_pct"], rows[self.KEY_A]["chhatni_status"]), (4.0, CHHATNI_RECEIVED))
		self.assertEqual((rows[self.KEY_B]["actual_chhatni_pct"], rows[self.KEY_B]["chhatni_status"]), (5.2, EXTRA_CHHATNI_RECEIVED))
		self.assertEqual(rows[self.KEY_B]["excess_received_qty"], 0.0)  # 260 - 250 - 13 < 0

	def test_same_chhatni_row_is_not_counted_twice(self):
		row = self._chhatni("CH-1", self.KEY_A, 10.0, 4.0)
		_, rows = self._run([self._grn(self.KEY_A, 280)], [row, row])
		self.assertEqual(rows[self.KEY_A]["chhatni_received_qty"], 10.0)
		self.assertEqual(rows[self.KEY_A]["actual_chhatni_pct"], 4.0)

	def test_two_records_of_one_pass_add_up(self):
		# Older data may hold two records; both use the pass TP Quantity, so QT and % add up.
		_, rows = self._run(
			[self._grn(self.KEY_A, 280)],
			[self._chhatni("CH-1", self.KEY_A, 5.0, 2.0), self._chhatni("CH-2", self.KEY_A, 5.0, 2.0)],
		)
		self.assertEqual((rows[self.KEY_A]["chhatni_received_qty"], rows[self.KEY_A]["actual_chhatni_pct"]), (10.0, 4.0))

	def test_pass_without_chhatni_record(self):
		_, rows = self._run([self._grn(self.KEY_A, 280)], [])
		row = rows[self.KEY_A]
		self.assertEqual((row["excess_received_qty"], row["actual_chhatni_pct"]), (30.0, 0.0))
		self.assertEqual(row["chhatni_status"], CHHATNI_PENDING)

	def test_chhatni_with_zero_values(self):
		_, rows = self._run([self._grn(self.KEY_A, 280)], [self._chhatni("CH-1", self.KEY_A, 0, 0)])
		self.assertEqual(rows[self.KEY_A]["actual_chhatni_pct"], 0.0)
		self.assertEqual(rows[self.KEY_A]["chhatni_status"], CHHATNI_PENDING)

	def test_tolerance_boundaries_on_saved_pct(self):
		cases = {4.30: CHHATNI_RECEIVED, 4.31: EXTRA_CHHATNI_RECEIVED, 3.70: CHHATNI_RECEIVED, 3.69: CHHATNI_PENDING}
		for pct, status in cases.items():
			_, rows = self._run([self._grn(self.KEY_A, 280)], [self._chhatni("CH-1", self.KEY_A, 10.0, pct)])
			self.assertEqual(rows[self.KEY_A]["chhatni_status"], status, pct)

	def test_columns_and_filters_preserved(self):
		from ivri_od.procurement.report.mandi_book.mandi_book import get_columns

		fieldnames = [column["fieldname"] for column in get_columns()]
		for fieldname in ("total_received", "excess_received_qty", "chhatni_assigned", "actual_chhatni_pct", "chhatni_status"):
			self.assertIn(fieldname, fieldnames)
		self.assertEqual(len(fieldnames), 35)  # same as before this change
		_, rows = self._run([self._grn(self.KEY_A, 280), self._grn(self.KEY_B, 260, tp_no="142")], [])
		with patch(f"{MANDI_BOOK}._rst_lines", return_value=[]):
			from ivri_od.procurement.report.mandi_book.mandi_book import execute

			_, filtered = execute({"transit_pass_no": "142"})
		self.assertEqual([row["pass_unique_key"] for row in filtered], [self.KEY_B])
