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

	# Weigh Bridge lines of a pass: by default gross = the GRN net weight, no gunny, no deduction.
	gunny_per_line = 0.0
	deduction_per_line = 0.0

	def _lines(self, docs, *args):
		return [
			{
				"gross_weight": float(doc.net_weight or 0), "gunny_weight": self.gunny_per_line,
				"deduction": self.deduction_per_line, "gunny_type": "", "jute_pkt": 0, "plastic_pkt": 0,
				"no_of_bags": 0, "total_bags": 0,
			}
			for doc in docs
		]

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
			patch(f"{MANDI_BOOK}._rst_lines", side_effect=self._lines),
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
		self.assertEqual(row["total_received"], 268.8)  # 280 gross - 11.2 Chhatni
		self.assertEqual(row["excess_received_qty"], 18.8)
		self.assertEqual(row["actual_chhatni_pct"], 4.48)
		self.assertEqual(row["chhatni_status"], EXTRA_CHHATNI_RECEIVED)
		self.assertEqual(row["chhatni_received_qty"], 11.2)

	def test_total_qty_received_is_gross_less_gunny_deduction_and_chhatni(self):
		self.gunny_per_line, self.deduction_per_line = 2.5, 1.5
		_, rows = self._run(
			[self._grn(self.KEY_A, 140), self._grn(self.KEY_A, 140)], [self._chhatni("CH-1", self.KEY_A, 11.2, 4.48)]
		)
		row = rows[self.KEY_A]
		self.assertEqual(
			(row["total_gross_weight"], row["total_gunny_weight"], row["total_deduction_received"], row["chhatni_received_qty"]),
			(280.0, 5.0, 3.0, 11.2),
		)
		self.assertEqual(row["total_received"], 260.8)  # 280 - 5 - 3 - 11.2

	def test_status_pending_and_excess_follow_the_new_total(self):
		# TP 250: 260.8 received -> completed, nothing pending, 10.8 excess.
		self.gunny_per_line, self.deduction_per_line = 2.5, 1.5
		_, rows = self._run(
			[self._grn(self.KEY_A, 140), self._grn(self.KEY_A, 140)], [self._chhatni("CH-1", self.KEY_A, 11.2, 4.48)]
		)
		row = rows[self.KEY_A]
		self.assertEqual((row["tp_status"], row["pending_qty"], row["excess_received_qty"]), ("TP Completed", 0.0, 10.8))
		# A bigger Chhatni pushes the same weighments below TP Qty: 280 - 5 - 3 - 30 = 242.
		_, rows = self._run(
			[self._grn(self.KEY_A, 140), self._grn(self.KEY_A, 140)], [self._chhatni("CH-1", self.KEY_A, 30.0, 12.0)]
		)
		row = rows[self.KEY_A]
		self.assertEqual(
			(row["total_received"], row["tp_status"], row["pending_qty"], row["excess_received_qty"]),
			(242.0, "In Progress", 8.0, 0.0),
		)

	def test_total_qty_received_never_goes_negative(self):
		self.deduction_per_line = 50.0
		_, rows = self._run([self._grn(self.KEY_A, 40)], [self._chhatni("CH-1", self.KEY_A, 5.0, 2.0)])
		row = rows[self.KEY_A]
		self.assertEqual((row["total_received"], row["tp_status"], row["pending_qty"]), (0.0, "Pending", 250.0))

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
		self.assertEqual(len(fieldnames), 36)  # the 35 existing columns plus Chhatni (QT)
		self.assertEqual(len(set(fieldnames)), 36)
		_, rows = self._run([self._grn(self.KEY_A, 280), self._grn(self.KEY_B, 260, tp_no="142")], [])
		with patch(f"{MANDI_BOOK}._rst_lines", return_value=[]):
			from ivri_od.procurement.report.mandi_book.mandi_book import execute

			_, filtered = execute({"transit_pass_no": "142"})
		self.assertEqual([row["pass_unique_key"] for row in filtered], [self.KEY_B])


class TestMandiBookChhatniColumnOrder(unittest.TestCase):
	"""Chhatni (QT) column and the exact column order. No site, no database."""

	def setUp(self):
		frappe.local.lang = "en"

	def test_columns_before_total_deduction_received_are_unchanged(self):
		from ivri_od.procurement.report.mandi_book.mandi_book import get_columns

		fieldnames = [column["fieldname"] for column in get_columns()]
		self.assertEqual(
			fieldnames[: fieldnames.index("total_deduction_received") + 1],
			[
				"season", "ppc_name", "mill_name", "transit_pass_no", "pass_unique_key", "tp_quantity",
				"total_gross_weight", "summary_gunny_type", "total_gunny_weight", "total_deduction_received",
			],
		)

	def test_requested_order_after_total_deduction_received(self):
		from ivri_od.procurement.report.mandi_book.mandi_book import get_columns

		columns = get_columns()
		fieldnames = [column["fieldname"] for column in columns]
		start = fieldnames.index("total_deduction_received") + 1
		self.assertEqual(
			fieldnames[start : start + 11],
			[
				"chhatni_received_qty", "total_received", "chhatni_assigned", "actual_chhatni_pct", "chhatni_status",
				"pending_qty", "excess_received_qty", "tp_status", "jute_pkt", "plastic_pkt", "total_bags",
			],
		)
		labels = {column["fieldname"]: column["label"] for column in columns}
		self.assertEqual(labels["chhatni_received_qty"], "Chhatni (QT)")
		# every other column follows the sequence, in its old order
		self.assertEqual(
			fieldnames[start + 11 :],
			[
				"entry", "agent_name", "entry_quantity", "entry_price_per_quintal", "total_amount", "grn_no", "rst_no",
				"vehicle_no", "load_weight", "tare_weight", "gross_weight", "gunny_type", "gunny_weight", "deduction",
				"net_weight",
			],
		)

	def test_chhatni_qt_column_reuses_the_existing_value(self):
		from ivri_od.procurement.report.mandi_book.mandi_book import get_columns

		column = next(c for c in get_columns() if c["fieldname"] == "chhatni_received_qty")
		self.assertEqual((column["fieldtype"], column["precision"]), ("Float", 3))

	def test_javascript_treats_the_new_column_as_a_summary_column(self):
		import pathlib

		import ivri_od.procurement.report.mandi_book as report

		js = (pathlib.Path(report.__file__).parent / "mandi_book.js").read_text()
		self.assertEqual(js.count('"chhatni_received_qty"'), 2)  # both summaryFieldnames sets
