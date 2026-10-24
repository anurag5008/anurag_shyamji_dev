# Copyright (c) 2026, Profezzo and Contributors
# See license.txt
"""Later corrections in RST Details / Quality Check must reach Weigh Bridge and the final GRN Note.

Mocked tests: no site, no database, no writes.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement.doctype.grn_note.grn_note import GRNNote
from ivri_od.procurement.doctype.quality_check.quality_check import QualityCheck
from ivri_od.procurement.doctype.rst_details.rst_details import RSTDetails
from ivri_od.procurement.doctype.weigh_bridge_measurement import weigh_bridge_measurement as wbm_module
from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	WeighBridgeMeasurement,
)

WBM = "ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement"
QC = "ivri_od.procurement.doctype.quality_check.quality_check"
RST = "ivri_od.procurement.doctype.rst_details.rst_details"


def _bare(cls, **values):
	"""Controller instance without Document.__init__ (which needs a site for meta)."""
	doc = cls.__new__(cls)
	doc.__dict__.update(values)
	doc.flags = frappe._dict()
	return doc


class TestEditPropagationNoDB(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.msgprint = MagicMock()

		def throw(msg, *args, **kwargs):
			raise frappe.ValidationError(msg)

		for name, value in (("db", self.db), ("msgprint", self.msgprint), ("throw", throw)):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	# --- Weigh Bridge -> GRN

	def test_existing_local_grn_keeps_syncing(self):
		"""Local paddy purchase GRN used to be skipped, so a corrected RST never reached it."""
		self.db.exists.return_value = True
		sync = MagicMock()
		with patch(f"{WBM}.is_local_procurement_wbm", return_value=True), patch(
			f"{WBM}.is_rice_dispatch_wbm", return_value=False
		), patch("ivri_od.procurement.doctype.grn_note.grn_note.sync_grn_from_weigh_bridge", sync):
			wbm_module._ensure_grn_note_for_weigh_bridge("WBM-1")
		sync.assert_called_once_with("WBM-1")

	def test_local_weighment_without_grn_still_creates_none(self):
		self.db.exists.side_effect = lambda doctype, *a, **k: doctype == "Weigh Bridge Measurement"
		build = MagicMock()
		with patch(f"{WBM}.is_local_procurement_wbm", return_value=True), patch(
			f"{WBM}.is_rice_dispatch_wbm", return_value=False
		), patch("ivri_od.procurement.doctype.grn_note.grn_note.build_auto_grn_doc_dict", build):
			wbm_module._ensure_grn_note_for_weigh_bridge("WBM-1")
		build.assert_not_called()

	# --- GRN fields: correction overwrites, first fill only fills blanks

	def _local_grn(self, syncing):
		grn = _bare(
			GRNNote,
			is_local_procurement=1,
			weigh_bridge_measurement="WBM-1",
			party_name="WRONG PARTY",
			ppc_name="WRONG PARTY",
			local_purchase_order="LPO-OLD",
			paddy_variety="OLD",
			receipt_datetime="2026-10-01 10:00:00",
		)
		grn.flags.syncing_from_wbm = syncing
		grn.get = lambda key, default=None: grn.__dict__.get(key, default)
		grn.set = lambda key, value: grn.__dict__.__setitem__(key, value)
		rst = frappe._dict(
			party_name="RIGHT PARTY", commodity="NEW", entry_date="2026-10-02", entry_time="09:00:00",
			agent_name="", local_purchase_order="LPO-NEW",
		)
		self.db.get_value.side_effect = [
			"RST-1",  # WBM demo_rst_data
			rst,  # RST Details row
		]
		self.db.exists.return_value = True
		return grn

	def test_sync_overwrites_local_grn_with_corrected_rst(self):
		grn = self._local_grn(syncing=True)
		with patch("ivri_od.procurement.doctype.grn_note.grn_note.ensure_doc_datetime"):
			grn._sync_local_procurement_from_rst()
		self.assertEqual(
			(grn.party_name, grn.ppc_name, grn.local_purchase_order, grn.paddy_variety),
			("RIGHT PARTY", "RIGHT PARTY", "LPO-NEW", "NEW"),
		)

	def test_plain_save_still_only_fills_blanks(self):
		grn = self._local_grn(syncing=False)
		grn._sync_local_procurement_from_rst()
		self.assertEqual(
			(grn.party_name, grn.ppc_name, grn.local_purchase_order, grn.paddy_variety),
			("WRONG PARTY", "WRONG PARTY", "LPO-OLD", "OLD"),
		)

	def test_quality_check_driver_is_overwritten_only_on_sync(self):
		qc = frappe._dict(
			moisture=15, dust=1, staff_name="S", unloading_point="U", paddy_type="", paddy_quality="",
			qc_decision="Accepted", paddy_received_in_pkt=10, paddy_returned=0, driver_name="NEW DRIVER",
			gate_entry="GE-1", qc_datetime=None,
		)
		for syncing, expected in ((True, "NEW DRIVER"), (False, "OLD DRIVER")):
			self.db.exists.return_value = True
			self.db.get_value.return_value = qc
			grn = _bare(GRNNote, is_local_procurement=0, driver_name="OLD DRIVER", no_of_bags=10, gate_entry="GE-1")
			grn.flags.syncing_from_wbm = syncing
			grn._apply_qc_bag_details = grn._apply_qc_old_new_bags = lambda name: None
			grn._apply_quality_check("QC-1")
			self.assertEqual(grn.driver_name, expected, syncing)

	def test_clear_quality_check_values(self):
		grn = _bare(GRNNote, moisture=15, dust=2, qc_decision="Accepted", driver_name="D", old_new_bags=[1], qc_bag_details=[1])
		grn.set = lambda key, value: grn.__dict__.__setitem__(key, value)
		grn._clear_quality_check_values()
		self.assertEqual((grn.moisture, grn.dust, grn.qc_decision, grn.driver_name), (0, 0, "", ""))
		self.assertEqual((grn.old_new_bags, grn.qc_bag_details, grn.qc_datetime), ([], [], None))

	# --- Quality Check: edit after Gate Exit, and vehicle correction

	def _qc(self, before_vehicle, before_gate, vehicle, gate):
		qc = _bare(QualityCheck, name="QC-2026-1", vehicle_no=vehicle, gate_entry=gate, driver_name="D")
		qc.get_doc_before_save = lambda: frappe._dict(vehicle_no=before_vehicle, gate_entry=before_gate)
		return qc

	def _gate_db(self, gate_vehicle, inside):
		self.db.exists.return_value = True
		self.db.get_value.side_effect = lambda doctype, *a, **k: (
			frappe._dict(vehicle_no=gate_vehicle, driver_name="D", in_out="In")
			if a and a[0] == "GE-1" or (a and a[0] == "GE-2")
			else None
		)
		return patch(f"{QC}.is_gate_in_inside_mill", return_value=inside)

	def test_edit_after_gate_exit_is_allowed_for_same_vehicle(self):
		qc = self._qc("CG04AA1111", "GE-1", "cg04aa1111", "GE-1")
		with self._gate_db("CG04AA1111", inside=False):
			qc._validate_gate_entry()  # the visit is closed, but the vehicle is unchanged: no "Visit Closed"
		self.assertEqual(qc.gate_entry, "GE-1")

	def test_new_quality_check_on_closed_visit_is_still_blocked(self):
		qc = _bare(QualityCheck, name="new", vehicle_no="CG04AA1111", gate_entry="GE-1", driver_name="")
		qc.get_doc_before_save = lambda: None
		with self._gate_db("CG04AA1111", inside=False), self.assertRaises(frappe.ValidationError):
			qc._validate_gate_entry()

	def test_corrected_vehicle_is_matched_to_its_own_open_gate_in(self):
		qc = self._qc("CG04AA1111", "GE-1", "CG04BB2222", "GE-1")
		with self._gate_db("CG04BB2222", inside=True), patch(
			f"{QC}._find_gate_entry_for_vehicle", return_value="GE-2"
		) as find:
			qc._validate_gate_entry()
		find.assert_called_once_with("CG04BB2222", exclude_qc="QC-2026-1")
		self.assertEqual((qc.gate_entry, qc.vehicle_no), ("GE-2", "CG04BB2222"))

	def test_corrected_vehicle_with_no_open_visit_is_refused(self):
		qc = self._qc("CG04AA1111", "GE-1", "CG04ZZ9999", "GE-1")
		with self._gate_db("CG04ZZ9999", inside=True), patch(
			f"{QC}._find_gate_entry_for_vehicle", return_value=None
		), patch(f"{QC}._gate_entry_lookup_error", return_value="not inside"), self.assertRaises(
			frappe.ValidationError
		):
			qc._validate_gate_entry()

	def test_vehicle_correction_unlinks_old_weighment_before_resync(self):
		qc = _bare(QualityCheck, name="QC-2026-1", vehicle_no="CG04BB2222", gate_entry="GE-2")
		qc.get_doc_before_save = lambda: frappe._dict(gate_entry="GE-1")
		order = MagicMock()
		with patch(f"{QC}.unlink_quality_check_from_weigh_bridge", order.unlink), patch(
			f"{QC}._sync_weigh_bridge_quality_from_qc", order.sync
		):
			qc.on_update()
		self.assertEqual([c[0] for c in order.mock_calls], ["unlink", "sync"])
		order.unlink.assert_called_once_with("QC-2026-1", "GE-2")

	def test_plain_qc_edit_does_not_unlink(self):
		qc = _bare(QualityCheck, name="QC-2026-1", vehicle_no="CG04AA1111", gate_entry="GE-1")
		qc.get_doc_before_save = lambda: frappe._dict(gate_entry="GE-1")
		with patch(f"{QC}.unlink_quality_check_from_weigh_bridge") as unlink, patch(
			f"{QC}._sync_weigh_bridge_quality_from_qc"
		):
			qc.on_update()
		unlink.assert_not_called()

	def test_unlink_returns_old_weighment_to_pending_qc_and_syncs_its_grn(self):
		with patch.object(frappe, "get_all", MagicMock(return_value=["WBM-1"]), create=True) as get_all, patch(
			f"{WBM}.persist_wbm_quality_and_net_after_qc_sync"
		) as persist, patch(f"{WBM}._ensure_grn_note_for_weigh_bridge") as ensure:
			names = wbm_module.unlink_quality_check_from_weigh_bridge("QC-2026-1", "GE-2")
		self.assertEqual(names, ["WBM-1"])
		self.assertEqual(
			get_all.call_args.kwargs["filters"], {"quality_check": "QC-2026-1", "gate_entry": ["!=", "GE-2"]}
		)
		values = self.db.set_value.call_args.args[2]
		self.assertEqual((values["quality_check"], values["quality_test"], values["slno_of_qc"]), ("", wbm_module.PENDING_QC, 0))
		persist.assert_called_once_with("WBM-1")
		ensure.assert_called_once_with("WBM-1")

	# --- TP No / PPC corrected on a weighment

	def test_pass_left_after_correction_is_refreshed(self):
		wbm = _bare(WeighBridgeMeasurement, pass_unique_key="NEW-KEY")
		wbm.get_doc_before_save = lambda: frappe._dict(pass_unique_key="OLD-KEY")
		self.db.after_commit = lambda fn: fn()
		with patch(f"{WBM}._sync_procurement_rollups_for_pass") as rollup, patch(
			f"{WBM}.refresh_tp_fulfillment_for_pass"
		) as refresh:
			wbm._refresh_pass_left_after_correction()
		rollup.assert_called_once_with("OLD-KEY")
		refresh.assert_called_once_with("OLD-KEY")

	def test_same_pass_is_not_refreshed_twice(self):
		wbm = _bare(WeighBridgeMeasurement, pass_unique_key="KEY")
		wbm.get_doc_before_save = lambda: frappe._dict(pass_unique_key="KEY")
		with patch(f"{WBM}.refresh_tp_fulfillment_for_pass") as refresh:
			wbm._refresh_pass_left_after_correction()
		refresh.assert_not_called()

	def test_corrected_vehicle_ignores_old_quality_check_link(self):
		wbm = _bare(WeighBridgeMeasurement, quality_check="QC-OLD", actual_truck_no="B", truck_no_in_tp="B", vehicle_no="B")
		wbm.get_doc_before_save = lambda: frappe._dict(actual_truck_no="A", truck_no_in_tp="A", vehicle_no="A")
		wbm.get = lambda key, default=None: wbm.__dict__.get(key, default)
		with patch(f"{WBM}.resolve_gate_entry_for_wbm_vehicle", return_value="GE-B") as resolve:
			wbm._sync_gate_entry_link()
		resolve.assert_called_once_with("B", None)
		self.assertEqual(wbm.gate_entry, "GE-B")

	# --- RST Details: unresolved correction never pushes bad data

	def test_rst_no_longer_matching_a_pass_clears_the_weighment(self):
		"""BADIMUNDA(S1050812) -> BADIMUND(S1050812): the weighment must not keep the old pass."""
		rst = _bare(
			RSTDetails, name="RST-1", rst_no="04", tp_no="146", party_name="BADIMUND (S1050812)",
			weigh_bridge_measurement="WBM-1", tp_status="PPC Mismatch", vehicle_no="od10d2348",
			gross_vehicle_weight_qt=0, tare_vehicle_weight_qt=0, deduction_qt=0, gunny_weight_qt=0,
			commodity="PADDY", entry_date="2026-10-24", entry_time="10:00:00",
		)
		wbm = MagicMock()
		self.db.exists.return_value = True
		with patch(f"{RST}.is_private_procurement_rst", return_value=False), patch(
			f"{RST}.party_found_awaiting_tp", return_value=False
		), patch(f"{RST}.try_get_matching_transit_pass", return_value=None), patch.object(
			frappe, "get_doc", MagicMock(return_value=wbm), create=True
		), patch(f"{WBM}.compute_wbm_tp_status", return_value="TP Not Received"):
			rst._sync_weigh_bridge_measurement()
		set_values = {c.args[0]: c.args[1] for c in wbm.set.call_args_list}
		for fieldname in ("pass_unique_key", "transit_pass_no", "pacs_name", "truck_no_in_tp", "agent_name"):
			self.assertEqual(set_values[fieldname], "", fieldname)
		self.assertEqual((set_values["tp_weight"], set_values["tp_status"]), (0, "TP Not Received"))
		self.assertEqual(set_values["actual_truck_no"], "OD10D2348")
		self.assertTrue(wbm.flags.ignore_mandatory)
		wbm.save.assert_called_once()
		self.assertIn("no longer show", self.msgprint.call_args.args[0])

	def test_unresolved_rst_is_not_tp_received_on_the_weighment(self):
		from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import compute_wbm_tp_status

		for rst_status, expected in (
			("PPC Mismatch", "PPC Mismatch"), ("Invalid TP No", "TP Not Received"), ("TP Received", "TP Received"),
		):
			rst = frappe._dict(tp_status=rst_status, tp_no="146", party_name="X")
			with patch.object(frappe, "get_doc", MagicMock(return_value=rst), create=True), patch(
				"ivri_od.procurement.doctype.rst_details.rst_details.is_private_procurement_rst", return_value=False
			), patch(
				"ivri_od.procurement.doctype.rst_details.rst_details.party_found_awaiting_tp", return_value=False
			):
				self.db.exists.return_value = True
				doc = frappe._dict(demo_rst_data="RST-1", pass_unique_key="")
				self.assertEqual(compute_wbm_tp_status(doc), expected, rst_status)

	def test_grn_drops_everything_from_the_pass_when_none_remains(self):
		grn = _bare(
			GRNNote, pass_unique_key="", mill_name="MILL", cmr_season="K25", transit_pass_no="146", pacs="P", ppc="BADIMUNDA(S1050812)",
			transit_pass_date="2026-10-01", transit_pass_datetime="x", tp_quantity=286.87, tp_cumulative_received=10,
			tp_cumulative_deduction=1, chhatni_received_pct=2, tp_chhatni_balance=3, tp_fulfillment_status="Pending",
			chhatni_fulfillment_status="Chhatni Pending", chhatni_fulfillment_remark="r",
		)
		grn.set = lambda key, value: grn.__dict__.__setitem__(key, value)
		grn._sync_from_transit_pass()
		self.db.get_value.assert_not_called()  # an empty key is never looked up
		for fieldname in ("mill_name", "cmr_season", "transit_pass_no", "pacs", "ppc", "tp_fulfillment_status", "chhatni_fulfillment_remark"):
			self.assertEqual(grn.__dict__[fieldname], "", fieldname)
		for fieldname in ("tp_quantity", "tp_cumulative_received", "tp_chhatni_balance", "chhatni_received_pct"):
			self.assertEqual(grn.__dict__[fieldname], 0, fieldname)
		self.assertIsNone(grn.transit_pass_datetime)

	def _new_rst(self, tp_status):
		return _bare(
			RSTDetails, name="RST-1", rst_no="04", tp_no="146", party_name="BADIMUND (S1050812)",
			weigh_bridge_measurement="", tp_status=tp_status, vehicle_no="od10d2348", commodity="PADDY",
			gross_vehicle_weight_qt=0, tare_vehicle_weight_qt=0, deduction_qt=0, gunny_weight_qt=0,
			entry_date="2026-10-24", entry_time="10:00:00",
		)

	def test_new_ppc_mismatch_rst_gets_a_weighment_with_that_status(self):
		rst = self._new_rst("PPC Mismatch")
		created = MagicMock()
		with patch(f"{RST}.is_private_procurement_rst", return_value=False), patch(
			f"{RST}.party_found_awaiting_tp", return_value=False
		), patch(f"{RST}.try_get_matching_transit_pass", return_value=None), patch(
			f"{WBM}.compute_wbm_tp_status", return_value="PPC Mismatch"
		), patch.object(frappe, "get_doc", MagicMock(return_value=created), create=True) as get_doc:
			rst.db_set = MagicMock()
			rst._sync_weigh_bridge_measurement()
		payload = get_doc.call_args.args[0]
		self.assertEqual(payload["doctype"], "Weigh Bridge Measurement")
		self.assertEqual((payload["tp_status"], payload["pass_unique_key"], payload["party_name"]), ("PPC Mismatch", "", "BADIMUND (S1050812)"))
		self.assertEqual((payload["rst_no"], payload["actual_truck_no"]), ("04", "OD10D2348"))
		self.assertTrue(created.flags.ignore_mandatory)
		created.insert.assert_called_once()
		self.msgprint.assert_not_called()

	def test_new_invalid_tp_no_rst_still_creates_no_weighment(self):
		rst = self._new_rst("Invalid TP No")
		with patch(f"{RST}.is_private_procurement_rst", return_value=False), patch(
			f"{RST}.party_found_awaiting_tp", return_value=False
		), patch(f"{RST}.try_get_matching_transit_pass", return_value=None), patch.object(
			frappe, "get_doc", MagicMock(), create=True
		) as get_doc:
			rst._sync_weigh_bridge_measurement()
		get_doc.assert_not_called()

	def test_rst_without_weighment_stays_silent(self):
		rst = _bare(RSTDetails, name="RST-1", rst_no="1", tp_no="TP-X", party_name="BAD", weigh_bridge_measurement="", tp_status="Invalid TP No")
		with patch(f"{RST}.is_private_procurement_rst", return_value=False), patch(
			f"{RST}.party_found_awaiting_tp", return_value=False
		), patch(f"{RST}.try_get_matching_transit_pass", return_value=None):
			rst._sync_weigh_bridge_measurement()
		self.msgprint.assert_not_called()


class TestDeductionFromRstOrQualityCheckNoDB(unittest.TestCase):
	"""Weigh Bridge Deduction (QT): RST Details first, else Quality Check Dust (Kg) / 100."""

	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		for name, value in (
			("db", self.db),
			("get_system_settings", MagicMock(return_value=None)),  # flt(x, 3) reads the rounding setting
		):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def _deduction(self, rst=None, dust=0, manual=0, rst_link="RST-1", qc="QC-1"):
		"""rst: RST Details Deduction (QT), None = RST record missing."""
		self.db.exists.return_value = rst is not None
		self.db.get_value.side_effect = lambda doctype, name, field: rst if doctype == "RST Details" else dust
		wbm = _bare(WeighBridgeMeasurement, demo_rst_data=rst_link, quality_check=qc, deduction=manual)
		wbm.get = lambda key, default=None: wbm.__dict__.get(key, default)
		wbm._sync_deduction()
		return wbm.deduction

	def test_rst_value_wins_over_quality_check(self):
		self.assertEqual(self._deduction(rst=1.25, dust=300), 1.25)

	def test_quality_check_dust_is_converted_from_kg_to_quintal(self):
		self.assertEqual(self._deduction(rst=0, dust=250), 2.5)
		self.assertEqual(self._deduction(rst=0, dust=12.5), 0.125)
		self.assertEqual(self._deduction(rst=0, dust=0.75), 0.008)  # rounds to the 3 decimals of the field

	def test_nothing_entered_anywhere_gives_zero(self):
		self.assertEqual(self._deduction(rst=0, dust=0), 0)
		self.assertEqual(self._deduction(rst=0, dust=0, qc=""), 0)

	def test_corrected_rst_value_replaces_the_quality_check_one(self):
		self.assertEqual(self._deduction(rst=0, dust=100), 1.0)
		self.assertEqual(self._deduction(rst=3, dust=100), 3.0)

	def test_manual_weighment_keeps_its_own_deduction(self):
		self.assertEqual(self._deduction(rst=None, rst_link="", dust=500, manual=0.4), 0.4)

	def test_manual_weighment_fills_empty_deduction_from_quality_check(self):
		self.assertEqual(self._deduction(rst=None, rst_link="", dust=500, manual=0), 5.0)

	def test_net_weight_uses_the_fetched_deduction(self):
		self.db.exists.return_value = True
		self.db.get_value.side_effect = lambda doctype, name, field: 0 if doctype == "RST Details" else 200
		wbm = _bare(
			WeighBridgeMeasurement, demo_rst_data="RST-1", quality_check="QC-1", deduction=0,
			load_weight=100, tare_weight=40, gunny_weight=0,
		)
		wbm.get = lambda key, default=None: wbm.__dict__.get(key, default)
		wbm._sync_total_bags_from_qc_table = lambda: None
		wbm._resolve_gunny_weight_qt = lambda: 0
		wbm._update_weights()
		self.assertEqual((wbm.deduction, wbm.gross_weight, wbm.net_weight), (2.0, 60, 58.0))


class TestGateEntryPartyNameIsStandaloneNoDB(unittest.TestCase):
	"""Gate Entry Party Name only stores data: Quality Check, GRN and Weigh Bridge never link to it."""

	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		for name, value in (("db", self.db), ("get_all", MagicMock(return_value=[]))):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_quality_check_save_never_writes_the_gate_entry(self):
		import ivri_od.procurement.doctype.quality_check.quality_check as qc_module

		self.assertFalse(hasattr(qc_module, "_sync_party_name_to_gate_entry"))
		qc = _bare(QualityCheck, name="QC-1", vehicle_no="CG04AA1111", gate_entry="GE-1", staff_name="STAFF")
		qc.get_doc_before_save = lambda: frappe._dict(gate_entry="GE-1")
		with patch(f"{QC}._sync_weigh_bridge_quality_from_qc"):
			qc.on_update()
		self.db.set_value.assert_not_called()

	def test_gate_entry_party_name_never_falls_back_to_quality_check(self):
		from ivri_od.procurement.doctype.gate_entry.gate_entry import party_name_for_gate_entry

		self.db.get_value.return_value = ""
		self.assertEqual(party_name_for_gate_entry("GE-1"), "")
		self.assertEqual(party_name_for_gate_entry("GE-1", doc=frappe._dict(party_name=" Typed Here ")), "Typed Here")
		frappe.get_all.assert_not_called()

	def test_grn_ignores_gate_entry_party_name(self):
		gate = frappe._dict(
			entry_datetime="2026-10-24 09:00:00", entry_date="2026-10-24", entry_time="09:00:00", driver_name="D",
			vehicle_no="CG04AA1111", party_name="GATE PARTY", mobile_no="99", in_out="In",
		)
		self.db.exists.return_value = True
		self.db.get_value.return_value = gate
		grn = _bare(GRNNote, party_name="QC STAFF", vehicle_no="CG04AA1111", driver_name="D")
		with patch("ivri_od.procurement.doctype.grn_note.grn_note._latest_gate_exit", return_value=None), patch(
			"ivri_od.procurement.doctype.grn_note.grn_note.ensure_doc_datetime"
		):
			grn._apply_gate_entry("GE-1")
		self.assertEqual(grn.party_name, "QC STAFF")

	def test_government_grn_party_comes_from_quality_check_local_keeps_rst_party(self):
		qc = frappe._dict(
			moisture=15, dust=1, staff_name=" QC STAFF ", unloading_point="U", paddy_type="", paddy_quality="",
			qc_decision="Accepted", paddy_received_in_pkt=10, paddy_returned=0, driver_name="D", gate_entry="GE-1",
			qc_datetime=None, is_farmer_or_agent=0, farmer_name="FARMER",
		)
		for local, farmer, expected in ((0, 0, "QC STAFF"), (0, 1, "FARMER"), (1, 0, "RST PARTY")):
			self.db.exists.return_value = True
			self.db.get_value.return_value = frappe._dict(qc, is_farmer_or_agent=farmer)
			grn = _bare(
				GRNNote, is_local_procurement=local, party_name="RST PARTY", driver_name="D", no_of_bags=10, gate_entry="GE-1"
			)
			grn._apply_qc_bag_details = grn._apply_qc_old_new_bags = lambda name: None
			grn._apply_quality_check("QC-1")
			self.assertEqual(grn.party_name, expected, (local, farmer))
