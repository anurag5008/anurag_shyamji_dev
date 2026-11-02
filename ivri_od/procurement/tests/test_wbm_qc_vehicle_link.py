# Copyright (c) 2026, Profezzo and Contributors
# See license.txt
"""A Quality Check is saved for one truck. It may only take over the weighments of THAT truck.

Incident: a weighment made on a substitute truck still carries the Transit Pass truck in `truck_no_in_tp`.
Saving the Quality Check of the Transit Pass truck matched it through that field and took over its
Quality Check, Gate Entry and bag count. A weighment belongs to its effective truck only.

Mocked tests: no site, no database.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	_wbm_names_matching_vehicle,
	find_wbm_names_for_quality_sync,
)

MODULE = "ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement"
TP_TRUCK = "OD03Y7755"  # the truck named on the Transit Pass
SUBSTITUTE = "CG15D5642"  # another truck that carried part of the same Transit Pass


def wbm(name, actual="", tp=TP_TRUCK, differs=0, vehicle="", farmer=0):
	"""A weighment row as the matching query returns it. `differs` is same_truck_as_transit_pass (1 = actual truck differs)."""
	return frappe._dict(
		name=name, actual_truck_no=actual, truck_no_in_tp=tp, vehicle_no=vehicle,
		same_truck_as_transit_pass=differs, is_farmer_or_agent=farmer,
	)


SUBSTITUTE_WBM = wbm("WBM-SUB", actual=SUBSTITUTE, differs=1)  # weighed on the substitute truck
TP_TRUCK_WBM = wbm("WBM-TP")  # weighed on the Transit Pass truck


class _NoSite(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		patcher = patch.object(frappe, "db", self.db, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def rows(self, *rows):
		self.db.sql.return_value = list(rows)


class TestWeighmentsMatchedToATruck(_NoSite):
	def test_transit_pass_truck_does_not_claim_a_weighment_made_on_another_truck(self):
		self.rows(SUBSTITUTE_WBM, TP_TRUCK_WBM)
		self.assertEqual(_wbm_names_matching_vehicle(TP_TRUCK), ["WBM-TP"])

	def test_the_substitute_truck_matches_its_own_weighment(self):
		self.rows(SUBSTITUTE_WBM)
		self.assertEqual(_wbm_names_matching_vehicle(SUBSTITUTE), ["WBM-SUB"])

	def test_when_the_actual_truck_is_not_entered_the_transit_pass_truck_is_the_truck(self):
		self.rows(wbm("WBM-A", actual="", differs=1))
		self.assertEqual(_wbm_names_matching_vehicle(TP_TRUCK), ["WBM-A"])

	def test_a_weighment_marked_as_the_same_truck_matches_the_transit_pass_truck(self):
		self.rows(wbm("WBM-B", actual="", differs=0))
		self.assertEqual(_wbm_names_matching_vehicle(TP_TRUCK), ["WBM-B"])

	def test_farmer_or_agent_weighment_matches_its_own_vehicle(self):
		self.rows(wbm("WBM-F", actual="OD11A1111", tp="", farmer=1, vehicle="OD11A1111"))
		self.assertEqual(_wbm_names_matching_vehicle("OD11A1111"), ["WBM-F"])

	def test_vehicle_numbers_are_compared_without_spaces_or_case(self):
		self.rows(TP_TRUCK_WBM)
		self.assertEqual(_wbm_names_matching_vehicle(" od03y7755 "), ["WBM-TP"])

	def test_a_blank_vehicle_matches_nothing_and_asks_nothing(self):
		self.assertEqual(_wbm_names_matching_vehicle(""), [])
		self.db.sql.assert_not_called()


class TestQualityCheckSyncTargets(_NoSite):
	"""find_wbm_names_for_quality_sync: the weighments a saved Quality Check is pushed to."""

	def setUp(self):
		super().setUp()
		self.db.exists.return_value = True
		self.db.get_value.side_effect = lambda doctype, name, field=None, **kw: {
			("Quality Check", "gate_entry"): "GE-TP",
			("Gate Entry", "vehicle_no"): TP_TRUCK,
		}.get((doctype, field))
		patcher = patch("frappe.get_all", return_value=["WBM-TP"])  # weighments already on this Gate Entry
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_qc_of_the_transit_pass_truck_does_not_take_the_substitute_trucks_weighment(self):
		self.rows(SUBSTITUTE_WBM, TP_TRUCK_WBM)
		self.assertEqual(set(find_wbm_names_for_quality_sync(TP_TRUCK, "QC-TP")), {"WBM-TP"})

	def test_qc_of_the_substitute_truck_reaches_only_its_own_weighment(self):
		self.rows(SUBSTITUTE_WBM, TP_TRUCK_WBM)
		with patch("frappe.get_all", return_value=["WBM-SUB"]):
			self.db.get_value.side_effect = lambda doctype, name, field=None, **kw: {
				("Quality Check", "gate_entry"): "GE-SUB",
				("Gate Entry", "vehicle_no"): SUBSTITUTE,
			}.get((doctype, field))
			self.assertEqual(set(find_wbm_names_for_quality_sync(SUBSTITUTE, "QC-SUB")), {"WBM-SUB"})

	def test_two_trucks_of_one_transit_pass_keep_separate_quality_checks(self):
		self.rows(SUBSTITUTE_WBM, TP_TRUCK_WBM)
		for_tp_truck = set(find_wbm_names_for_quality_sync(TP_TRUCK, "QC-TP"))
		self.assertTrue(for_tp_truck.isdisjoint({"WBM-SUB"}))


if __name__ == "__main__":
	unittest.main()
