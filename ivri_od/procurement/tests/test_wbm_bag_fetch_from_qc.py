# Copyright (c) 2026, Profezzo and Contributors
# See license.txt
"""Weigh Bridge Bag Details always mirror the linked Quality Check.

- a linked QC gives its Jute Bag No / Plastic Bag No / Total Bags, also when the QC is saved after the weighment;
- a changed QC replaces the rows with the new QC's lines;
- no QC (or one without bag lines) leaves no rows and Total Bags 0, never the lines of a QC the weighment left;
- the entered per-bag weights are kept by row.

Mocked tests: no site, no database.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import frappe

from ivri_od.procurement.doctype.weigh_bridge_measurement import weigh_bridge_measurement as wbm_module
from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	WeighBridgeMeasurement,
	_ensure_wbm_bag_details_from_qc,
	unlink_quality_check_from_weigh_bridge,
)

MODULE = "ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement"


def row(jute=0, plastic=0, w_jute=0.0, w_plastic=0.0):
	return SimpleNamespace(
		jute_bags=jute, plastic_bags=plastic, total_bags=jute + plastic,
		weight_per_jute_kg=w_jute, weight_per_plastic_kg=w_plastic,
		jute_total_qt=0, plastic_total_qt=0, gunny_weight_qt=0,
	)


class _Wbm:
	"""Just enough of a Weigh Bridge Measurement for the Bag Details methods."""

	def __init__(self, quality_check="", rows=()):
		self.quality_check = quality_check
		self.bag_weight_details = list(rows)
		self.total_bags = sum(r.jute_bags + r.plastic_bags for r in rows)
		self.flags = SimpleNamespace()
		self.save = MagicMock()

	def append(self, fieldname, values):
		new = row()
		self.bag_weight_details.append(new)
		return new

	_sync_bag_details_from_qc = WeighBridgeMeasurement._sync_bag_details_from_qc
	_persist_bag_details_from_qc = WeighBridgeMeasurement._persist_bag_details_from_qc
	_sync_total_bags_from_qc_table = WeighBridgeMeasurement._sync_total_bags_from_qc_table
	_total_bags_from_qc_table = WeighBridgeMeasurement._total_bags_from_qc_table


class _NoSite(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.db.exists.return_value = True
		patcher = patch.object(frappe, "db", self.db, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def qc_lines(self, *lines):
		"""The packet lines of the linked Quality Check, as (jute, plastic)."""
		patcher = patch(f"{MODULE}._qc_bag_lines", return_value=[{"jute_pkt_no": j, "no_of_plastic_bag": p} for j, p in lines])
		patcher.start()
		self.addCleanup(patcher.stop)


class TestBagDetailsMirrorTheLinkedQc(_NoSite):
	def test_a_linked_qc_gives_its_jute_plastic_and_total_bags(self):
		self.qc_lines((120, 48))
		wbm = _Wbm("QC-1")
		wbm._sync_bag_details_from_qc()
		self.assertEqual([(r.jute_bags, r.plastic_bags, r.total_bags) for r in wbm.bag_weight_details], [(120, 48, 168)])
		self.assertEqual(wbm.total_bags, 168)

	def test_a_qc_saved_after_the_weighment_fills_the_empty_table(self):
		wbm = _Wbm("", [])  # weighed first: no QC, no rows
		wbm._sync_bag_details_from_qc()
		self.assertEqual((wbm.bag_weight_details, wbm.total_bags), ([], 0))
		self.qc_lines((0, 196))
		wbm.quality_check = "QC-9"  # the QC arrives
		wbm._sync_bag_details_from_qc()
		self.assertEqual((len(wbm.bag_weight_details), wbm.total_bags), (1, 196))

	def test_a_changed_qc_replaces_the_rows_with_the_new_qcs_lines(self):
		self.qc_lines((150, 0))
		wbm = _Wbm("QC-2", [row(0, 168)])  # rows were fetched from the previous QC
		wbm._sync_bag_details_from_qc()
		self.assertEqual([(r.jute_bags, r.plastic_bags) for r in wbm.bag_weight_details], [(150, 0)])
		self.assertEqual(wbm.total_bags, 150)

	def test_no_qc_leaves_no_rows_and_zero_total(self):
		wbm = _Wbm("", [row(150, 0)])
		wbm._sync_bag_details_from_qc()
		self.assertEqual((wbm.bag_weight_details, wbm.total_bags), ([], 0))

	def test_a_qc_without_bag_lines_does_not_keep_another_qcs_bags(self):
		self.qc_lines()  # the linked QC has no packet lines
		wbm = _Wbm("QC-LEGACY", [row(150, 0)])
		wbm._sync_bag_details_from_qc()
		self.assertEqual((wbm.bag_weight_details, wbm.total_bags), ([], 0))

	def test_a_qc_record_that_does_not_exist_leaves_no_rows(self):
		self.db.exists.return_value = False
		wbm = _Wbm("QC-GONE", [row(150, 0)])
		wbm._sync_bag_details_from_qc()
		self.assertEqual((wbm.bag_weight_details, wbm.total_bags), ([], 0))

	def test_entered_weights_are_kept_by_row_when_the_bags_are_fetched_again(self):
		self.qc_lines((100, 0))
		# frappe.flt needs a site (it reads system settings); plain rounding is enough for this check
		patcher = patch(f"{MODULE}._trim_qty", side_effect=lambda v, d=3: round(float(v or 0), d))
		patcher.start()
		self.addCleanup(patcher.stop)
		wbm = _Wbm("QC-1", [row(100, 0, w_jute=1.5)])
		wbm._sync_bag_details_from_qc()
		self.assertEqual(wbm.bag_weight_details[0].weight_per_jute_kg, 1.5)
		self.assertEqual(wbm.bag_weight_details[0].jute_total_qt, 1.5)  # 1.5 kg x 100 bags = 150 kg = 1.5 QT


class TestPersistingBagDetails(_NoSite):
	def test_persist_writes_the_qc_lines(self):
		self.qc_lines((10, 5))
		wbm = _Wbm("QC-1")
		wbm._persist_bag_details_from_qc()
		self.assertEqual(wbm.total_bags, 15)
		wbm.save.assert_called_once_with(ignore_permissions=True)
		self.assertTrue(wbm.flags.ignore_validate)

	def test_persist_also_empties_the_table_when_there_is_no_qc(self):
		wbm = _Wbm("", [row(150, 0)])
		wbm._persist_bag_details_from_qc()
		self.assertEqual((wbm.bag_weight_details, wbm.total_bags), ([], 0))
		wbm.save.assert_called_once()


class TestEnsureBagDetails(_NoSite):
	def setUp(self):
		super().setUp()
		self.doc = MagicMock()
		for target, value in (("frappe.get_doc", self.doc), ("frappe.get_all", MagicMock())):
			patcher = patch(target, return_value=value if target == "frappe.get_doc" else [])
			mock = patcher.start()
			self.addCleanup(patcher.stop)
			if target == "frappe.get_all":
				self.get_all = mock

	def _ensure(self, existing, qc, details, stored_qc=""):
		self.get_all.return_value = [SimpleNamespace(jute_bags=j, plastic_bags=p) for j, p in existing]
		self.db.get_value.return_value = stored_qc
		_ensure_wbm_bag_details_from_qc("WBM-1", {"quality_check": qc, "bag_details": [{"jute_bags": j, "plastic_bags": p} for j, p in details]})

	def test_rows_that_match_the_qc_are_left_alone(self):
		self._ensure([(120, 48)], "QC-1", [(120, 48)], stored_qc="QC-1")
		self.doc._persist_bag_details_from_qc.assert_not_called()

	def test_rows_that_differ_from_the_qc_are_rewritten(self):
		self._ensure([(0, 168)], "QC-1", [(150, 0)], stored_qc="QC-1")
		self.doc._persist_bag_details_from_qc.assert_called_once()

	def test_stale_rows_are_removed_when_the_weighment_has_no_qc(self):
		self._ensure([(150, 0)], "", [], stored_qc="")
		self.doc._persist_bag_details_from_qc.assert_called_once()

	def test_stale_rows_are_removed_when_the_qc_has_no_bag_lines(self):
		self._ensure([(150, 0)], "QC-LEGACY", [], stored_qc="QC-LEGACY")
		self.doc._persist_bag_details_from_qc.assert_called_once()

	def test_nothing_is_written_when_there_is_nothing_to_remove(self):
		self._ensure([], "", [], stored_qc="")
		self.doc._persist_bag_details_from_qc.assert_not_called()

	def test_a_lookup_that_finds_no_qc_does_not_override_a_weighment_that_is_still_linked(self):
		self._ensure([(150, 0)], "", [], stored_qc="QC-1")
		self.doc._persist_bag_details_from_qc.assert_not_called()


class TestQcMovedToAnotherVisit(_NoSite):
	def test_the_old_weighments_lose_their_bags_with_the_qc_link_before_weights_are_recalculated(self):
		order = MagicMock()
		with patch("frappe.get_all", return_value=["WBM-1"]), patch(f"{MODULE}._ensure_wbm_bag_details_from_qc", order.ensure), \
			patch(f"{MODULE}.persist_wbm_quality_and_net_after_qc_sync", order.net), \
			patch(f"{MODULE}._ensure_grn_note_for_weigh_bridge", order.grn):
			self.db.set_value = order.set_value
			result = unlink_quality_check_from_weigh_bridge("QC-1", "GE-NEW")
		self.assertEqual(result, ["WBM-1"])
		names = [c[0] for c in order.mock_calls]
		self.assertEqual(names, ["set_value", "ensure", "net", "grn"])
		self.assertEqual(order.ensure.call_args, call("WBM-1", {"quality_check": "", "bag_details": []}))
		self.assertEqual(order.set_value.call_args.args[2]["quality_check"], "")


class TestBagDetailsAreShown(unittest.TestCase):
	"""The table is on the form for every weighment, not only Gunny Cut: it is the QC's data, read only."""

	def setUp(self):
		import json
		from pathlib import Path

		base = Path(__file__).resolve().parents[1] / "doctype"
		self.wbm = {f["fieldname"]: f for f in json.loads((base / "weigh_bridge_measurement/weigh_bridge_measurement.json").read_text())["fields"]}
		self.child = {f["fieldname"]: f for f in json.loads((base / "weigh_bridge_bag_detail/weigh_bridge_bag_detail.json").read_text())["fields"]}

	def test_the_table_has_no_condition_and_is_read_only(self):
		table = self.wbm["bag_weight_details"]
		self.assertEqual((table["fieldtype"], table["options"], table.get("read_only")), ("Table", "Weigh Bridge Bag Detail", 1))
		self.assertNotIn("depends_on", table)
		self.assertNotIn("hidden", table)

	def test_the_rows_show_jute_plastic_and_total_bags(self):
		for name, label in (("jute_bags", "Jute Bag No (Bags)"), ("plastic_bags", "Plastic Bag No (Bags)"), ("total_bags", "Total Bags")):
			field = self.child[name]
			self.assertEqual((field["label"], field.get("in_list_view"), field.get("read_only")), (label, 1, 1), name)
			self.assertNotIn("hidden", field)
			self.assertNotIn("depends_on", field)


if __name__ == "__main__":
	unittest.main()
