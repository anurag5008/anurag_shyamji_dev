# Copyright (c) 2026, Profezzo and Contributors
# See license.txt
"""GRN Note is auto-generated after Gate Exit, not at tare weight.

Mocked tests: no site, no database.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement.doctype.gate_exit.gate_exit import GateExit
from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	_ensure_grn_note_for_weigh_bridge,
	create_grn_notes_after_gate_exit,
	grn_pending_reasons_for_wbm,
	wbm_gate_entry_in,
	wbm_vehicle_has_exited,
)

MODULE = "ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement"
GRN_MODULE = "ivri_od.procurement.doctype.grn_note.grn_note"


class _NoSite(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.msgprint = MagicMock()
		for name, value in (("db", self.db), ("msgprint", self.msgprint)):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def patch(self, target, **kwargs):
		patcher = patch(target, **kwargs)
		mock = patcher.start()
		self.addCleanup(patcher.stop)
		return mock


class TestEnsureGrnWaitsForGateExit(_NoSite):
	def setUp(self):
		super().setUp()
		self.patch(f"{MODULE}.is_local_procurement_wbm", return_value=False)
		self.sync = self.patch(f"{GRN_MODULE}.sync_grn_from_weigh_bridge")
		self.build = self.patch(f"{GRN_MODULE}.build_auto_grn_doc_dict", return_value={"doctype": "GRN Note"})
		self.grn = MagicMock(flags=frappe._dict())
		self.patch("frappe.get_doc", return_value=self.grn)

	def _ensure(self, grn_exists, exited):
		# exists(): first call checks the WBM, second checks for an existing GRN
		self.db.exists.side_effect = [True, grn_exists]
		self.patch(f"{MODULE}.wbm_vehicle_has_exited", return_value=exited)
		_ensure_grn_note_for_weigh_bridge("WBM-1")

	def test_no_grn_after_tare_while_vehicle_inside(self):
		self._ensure(grn_exists=False, exited=False)
		self.build.assert_not_called()
		self.grn.insert.assert_not_called()

	def test_grn_created_once_vehicle_exited(self):
		self._ensure(grn_exists=False, exited=True)
		self.build.assert_called_once_with("WBM-1")
		self.grn.insert.assert_called_once_with(ignore_permissions=True)
		self.assertTrue(self.grn.flags.auto_from_wbm)

	def test_existing_grn_keeps_syncing_while_inside(self):
		self._ensure(grn_exists=True, exited=False)
		self.sync.assert_called_once_with("WBM-1")
		self.build.assert_not_called()


class TestVisitOfWeighment(_NoSite):
	def _row(self, gate_entry="", **values):
		return frappe._dict(
			gate_entry=gate_entry,
			actual_truck_no=values.get("actual_truck_no", ""),
			truck_no_in_tp=values.get("truck_no_in_tp", "OD03AB4135"),
			vehicle_no="",
			same_truck_as_transit_pass=0,
			creation="2026-10-22 10:00:00",
		)

	def test_linked_gate_in(self):
		self.db.get_value.side_effect = [self._row("GE-1"), "In"]
		self.assertEqual(wbm_gate_entry_in("WBM-1"), "GE-1")

	def test_linked_gate_out_maps_to_its_gate_in(self):
		self.db.get_value.side_effect = [self._row("GE-OUT"), "Out", "GE-1"]
		self.assertEqual(wbm_gate_entry_in("WBM-1"), "GE-1")

	def test_unlinked_uses_vehicle_gate_in_before_weighment(self):
		self.db.get_value.return_value = self._row()
		self.db.sql.return_value = [["GE-2"]]
		self.assertEqual(wbm_gate_entry_in("WBM-1"), "GE-2")
		self.assertEqual(self.db.sql.call_args.args[1], ("OD03AB4135", "2026-10-22 10:00:00"))

	def test_unlinked_without_gate_in(self):
		self.db.get_value.return_value = self._row()
		self.db.sql.return_value = []
		self.assertEqual(wbm_gate_entry_in("WBM-1"), "")

	def test_has_exited(self):
		self.patch(f"{MODULE}.wbm_gate_entry_in", return_value="GE-1")
		self.db.get_value.return_value = "In"
		with patch(f"{MODULE}.is_gate_in_inside_mill", return_value=True):
			self.assertFalse(wbm_vehicle_has_exited("WBM-1"))
		with patch(f"{MODULE}.is_gate_in_inside_mill", return_value=False):
			self.assertTrue(wbm_vehicle_has_exited("WBM-1"))

	def test_no_visit_means_not_exited(self):
		self.patch(f"{MODULE}.wbm_gate_entry_in", return_value="")
		self.assertFalse(wbm_vehicle_has_exited("WBM-1"))


class TestCreateGrnOnGateExit(_NoSite):
	def test_creates_for_linked_and_unlinked_weighments_of_this_visit(self):
		self.db.get_value.side_effect = lambda doctype, *a, **k: (
			frappe._dict(vehicle_no=" od03ab4135 ", creation="2026-10-22 09:00:00")
			if doctype == "Gate Entry"
			else {"WBM-1": None, "WBM-2": None, "WBM-3": "GRN-OLD"}.get(self._last_wbm)
		)
		unlinked = [
			frappe._dict(name="WBM-2", actual_truck_no="", truck_no_in_tp="OD03AB4135", vehicle_no="", same_truck_as_transit_pass=0),
			frappe._dict(name="WBM-9", actual_truck_no="", truck_no_in_tp="OTHER", vehicle_no="", same_truck_as_transit_pass=0),
		]
		self.patch("frappe.get_all", side_effect=[["WBM-1", "WBM-3"], unlinked])
		visits = {"WBM-1": "GE-1", "WBM-2": "GE-1", "WBM-3": "GE-1"}
		self.patch(f"{MODULE}.wbm_gate_entry_in", side_effect=lambda name: visits[name])
		self.db.exists.side_effect = lambda doctype, filters: filters["weigh_bridge_measurement"] == "WBM-3"

		def ensure(name):
			self._last_wbm = name
			if name != "WBM-3":
				self.db.get_value.side_effect = lambda doctype, *a, **k: f"GRN-{name}"

		self._last_wbm = None
		ensure_mock = self.patch(f"{MODULE}._ensure_grn_note_for_weigh_bridge", side_effect=ensure)
		created = create_grn_notes_after_gate_exit("GE-1")
		self.assertEqual([c.args[0] for c in ensure_mock.call_args_list], ["WBM-1", "WBM-3", "WBM-2"])
		self.assertEqual(created, ["GRN-WBM-1", "GRN-WBM-2"])  # WBM-3 already had a GRN

	def test_skips_unlinked_weighment_of_a_later_visit(self):
		self.db.get_value.return_value = frappe._dict(vehicle_no="OD03AB4135", creation="2026-10-22 09:00:00")
		unlinked = [frappe._dict(name="WBM-2", actual_truck_no="OD03AB4135", truck_no_in_tp="", vehicle_no="", same_truck_as_transit_pass=1)]
		self.patch("frappe.get_all", side_effect=[[], unlinked])
		self.patch(f"{MODULE}.wbm_gate_entry_in", return_value="GE-LATER")
		ensure_mock = self.patch(f"{MODULE}._ensure_grn_note_for_weigh_bridge")
		self.assertEqual(create_grn_notes_after_gate_exit("GE-1"), [])
		ensure_mock.assert_not_called()

	def test_unknown_gate_in(self):
		self.db.get_value.return_value = None
		self.assertEqual(create_grn_notes_after_gate_exit("NOPE"), [])

	def test_gate_exit_save_creates_grn_and_informs(self):
		doc = GateExit.__new__(GateExit)
		doc.gate_entry_in = "GE-1"
		with patch(f"{MODULE}.create_grn_notes_after_gate_exit", return_value=["GRN-1"]) as create:
			doc.on_update()
		create.assert_called_once_with("GE-1")
		self.db.set_value.assert_called_once_with("Gate Entry", "GE-1", "inside_mill", 0, update_modified=False)
		self.assertIn("GRN-1", self.msgprint.call_args.args[0])

	def test_gate_exit_without_weighment_is_silent(self):
		doc = GateExit.__new__(GateExit)
		doc.gate_entry_in = "GE-1"
		with patch(f"{MODULE}.create_grn_notes_after_gate_exit", return_value=[]):
			doc.on_update()
		self.msgprint.assert_not_called()


class TestPendingReasons(_NoSite):
	def test_pending_reason_until_exit(self):
		wbm = frappe._dict(tare_weight=200, pass_unique_key="KEY", rst_no="401", is_farmer_or_agent=0)
		self.db.exists.side_effect = [True, False]  # WBM exists, no GRN yet
		self.db.get_value.return_value = wbm
		self.patch(f"{MODULE}.is_local_procurement_wbm", return_value=False)
		with patch(f"{MODULE}.wbm_vehicle_has_exited", return_value=False):
			self.assertEqual(grn_pending_reasons_for_wbm("WBM-1"), ["Vehicle has not exited yet. The GRN is created after Gate Exit."])
		self.db.exists.side_effect = [True, False]
		with patch(f"{MODULE}.wbm_vehicle_has_exited", return_value=True):
			self.assertEqual(grn_pending_reasons_for_wbm("WBM-1"), [])


if __name__ == "__main__":
	unittest.main()
