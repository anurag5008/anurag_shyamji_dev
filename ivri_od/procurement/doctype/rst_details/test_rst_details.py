# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ivri_od.procurement.doctype.rst_details.rst_details import (
	RSTDetails,
	fetch_mill_and_agent_from_tp,
	resolve_rst_tp_details,
	try_get_matching_transit_pass,
)

MODULE = "ivri_od.procurement.doctype.rst_details.rst_details"


class TestRSTDetailsTPLogicNoDB(unittest.TestCase):
	"""Mocked tests: no site, no database."""

	def setUp(self):
		frappe.local.lang = "en"
		frappe.local._party_matches_any_transit_pass_ppc = {}
		# No site is bound, so stub frappe.throw (needs frappe.flags), frappe.msgprint and frappe.db.
		def throw(msg, *args, **kwargs):
			raise frappe.ValidationError(msg)

		self.db = MagicMock()
		self.msgprint = MagicMock()
		for name, value in (("throw", throw), ("db", self.db), ("msgprint", self.msgprint)):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		# PPC Master lookups need a database; tests that need one patch it again.
		patcher = patch(f"{MODULE}.resolve_ppc_master_name", return_value=None)
		patcher.start()
		self.addCleanup(patcher.stop)
		patcher = patch(f"{MODULE}.ppc_master_candidates", return_value=[])
		patcher.start()
		self.addCleanup(patcher.stop)
		# Depo Master lookups need a database: no depo matches unless a test says so.
		patcher = patch(f"{MODULE}.party_matches_depo_master", return_value=False)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _set_status(self, tp_no, party_name, rows=(), tp_exists=False):
		doc = RSTDetails.__new__(RSTDetails)
		doc.tp_no, doc.party_name, doc.tp_status = tp_no, party_name, "TP Received"
		doc.mill_name, doc.agent_name = "OLD-MILL", "OLD-AGENT"
		doc.entry_datetime = doc.entry_date = None
		doc.meta = MagicMock()  # meta is a cached_property, so this skips the database
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=list(rows)), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=tp_exists
		):
			doc._set_tp_status()
		return doc

	def test_mismatched_ppc_saves_as_ppc_mismatch(self):
		doc = self._set_status("TP-1", "WRONG", tp_exists=True)
		self.assertEqual(doc.tp_status, "PPC Mismatch")
		self.assertEqual(doc.mill_name, "")
		self.assertEqual(doc.agent_name, "")
		self.msgprint.assert_called_once()
		self.assertIn("Enter Correct PPC Name.", self.msgprint.call_args.args[0])

	def test_unknown_tp_no_saves_as_invalid_tp_no(self):
		"""validate() re-runs the rules and never trusts the status the form set."""
		doc = self._set_status("NOPE", "AGALPUR(S1)", tp_exists=False)
		self.assertEqual(doc.tp_status, "Invalid TP No")
		self.assertEqual(doc.mill_name, "")
		self.msgprint.assert_called_once()
		self.assertIn("Invalid TP No. NOPE", self.msgprint.call_args.args[0])

	def test_valid_statuses_do_not_notify(self):
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=True), patch(
			f"{MODULE}.get_agent_for_ppc_text", return_value="AGENT-1"
		):
			doc = self._set_status("", "AGALPUR(S1)")
		self.assertEqual(doc.tp_status, "TP No Not Received")
		self.msgprint.assert_not_called()

	def test_wrong_name_with_right_code_is_ppc_mismatch(self):
		"""Bug: "WRONG(S1)" matched "AGALPUR(S1)" by code alone and got TP Received."""
		rows = [{"pass_unique_key": "M051007-X", "ppc": "AGALPUR(S1)", "miller": ""}]
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=True
		), patch(f"{MODULE}.get_agent_for_ppc_text", return_value="AGENT-1"):
			wrong = resolve_rst_tp_details("TP-1", "ZZ WRONG(S1)")
			right = resolve_rst_tp_details("TP-1", "agalpur (S1)")
		self.assertEqual(wrong["tp_status"], "PPC Mismatch")
		self.assertEqual(wrong["mill_name"], "")
		self.assertEqual(wrong["notification"], "Enter Correct PPC Name.")
		self.assertEqual(right["tp_status"], "TP Received")

	def test_pass_text_spelled_differently_from_master_still_matches(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import party_ppc_match_state as state

		# Master says AGALPUR, the pass says AGALPUR SCS: the user may type either, never another name.
		with patch(f"{MODULE}.resolve_ppc_master_name", return_value="S1"), patch(
			f"{MODULE}.ppc_master_candidates", return_value=[]
		):
			self.assertEqual(state("Agalpur SCS(S1)", "AGALPUR SCS(S1)"), "match")
			self.assertEqual(state("S1", "AGALPUR SCS(S1)"), "match")
			self.assertEqual(state("Other(S1)", "AGALPUR SCS(S1)"), "mismatch")

	def test_invalid_tp_no_takes_priority_over_ppc_mismatch(self):
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=[]), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=False
		):
			for party_name in ("AGALPUR(S1)", "Unknown Party"):
				res = resolve_rst_tp_details("NOPE", party_name)
				self.assertEqual(res["tp_status"], "Invalid TP No")
				self.assertIn("Invalid TP No. NOPE", res["notification"])
				self.assertEqual(res["validation_message"], "")

	def test_duplicate_transit_pass_is_never_silently_picked(self):
		rows = [
			{"pass_unique_key": "M1-A", "ppc": "PPC(S1)"},
			{"pass_unique_key": "M2-A", "ppc": "PPC(S1)"},
		]
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows):
			res = resolve_rst_tp_details("TP-1", "PPC(S1)")
		self.assertEqual(res["tp_status"], "")
		self.assertEqual(res["mill_name"], "")
		self.assertIn("More than one", res["validation_message"])

	def test_tp_received_sets_mill_and_agent(self):
		rows = [{"pass_unique_key": "M051007-X", "ppc": "PPC(S1)", "miller": ""}]
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows), patch(
			f"{MODULE}.get_agent_for_ppc_text", return_value="AGENT-1"
		):
			res = resolve_rst_tp_details("TP-1", "PPC(S1)")
		self.assertEqual(res["tp_status"], "TP Received")
		self.assertEqual(res["mill_name"], "M051007")
		self.assertEqual(res["agent_name"], "AGENT-1")

	def test_save_clears_stale_mill_and_agent_when_not_resolved(self):
		doc = RSTDetails.__new__(RSTDetails)
		doc.tp_no, doc.party_name = "", "Local Farmer"
		doc.mill_name, doc.agent_name = "OLD-MILL", "OLD-AGENT"
		doc.entry_datetime = doc.entry_date = None
		doc.meta = MagicMock()  # meta is a cached_property, so this skips the database
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=False):
			doc._set_tp_status()
		self.assertEqual(doc.tp_status, "Local Paddy Purchase")
		self.assertEqual(doc.mill_name, "")
		self.assertEqual(doc.agent_name, "")

	def test_party_lookup_uses_authoritative_match_and_is_cached(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import party_matches_any_transit_pass_ppc

		self.db.sql.return_value = [{"ppc": "SAME NAME(S2)"}]
		with patch(f"{MODULE}.resolve_ppc_master_name", return_value=None), patch(
			f"{MODULE}.party_ppc_match_state", return_value="mismatch"
		) as match:
			self.assertFalse(party_matches_any_transit_pass_ppc("Same Name"))
			self.assertFalse(party_matches_any_transit_pass_ppc("same name"))
		match.assert_called_once()
		self.db.sql.assert_called_once()

	def test_party_lookup_rejects_wrong_name_with_right_code(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import party_matches_any_transit_pass_ppc

		self.db.sql.return_value = [{"ppc": "AGALPUR(S1)"}]
		if True:
			self.assertFalse(party_matches_any_transit_pass_ppc("ZZ WRONG(S1)"))
			self.assertTrue(party_matches_any_transit_pass_ppc("AGALPUR(S1)"))


class TestRSTUniqueKeyNoDB(unittest.TestCase):
	"""Mocked tests for Season Code and RST Unique Key: no site, no database."""

	KHARIF = {"pass_unique_key": "M051007-G S DUNGURIPALI(S1050807)-K25-TP18", "ppc": "G S DUNGURIPALI(S1050807)"}
	RABI = {"pass_unique_key": "M051007-G S DUNGURIPALI(S1050807)-R25-TP18", "ppc": "G S DUNGURIPALI(S1050807)"}

	def setUp(self):
		frappe.local.lang = "en"
		self.msgprint = MagicMock()
		patchers = [
			patch.object(frappe, "msgprint", self.msgprint, create=True),
			patch.object(frappe, "db", MagicMock(), create=True),
			patch(f"{MODULE}.resolve_ppc_master_name", return_value=None),
			patch(f"{MODULE}.ppc_master_candidates", return_value=[]),
			patch(f"{MODULE}.party_matches_depo_master", return_value=False),
			patch(f"{MODULE}.get_agent_for_ppc_text", return_value=""),
			patch(f"{MODULE}.transit_pass_no_exists", return_value=True),
			# Season of a pass = the K25 / R25 part of its Pass Unique Key.
			patch(
				f"{MODULE}._transit_pass_matches_season",
				side_effect=lambda row, season: f"-{season[0]}25-" in row["pass_unique_key"],
			),
			patch(f"{MODULE}.get_season_code", side_effect=lambda season: f"{season[0]}25"),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

	def _resolve(self, rows, season, tp_no="18", party="G S DUNGURIPALI(S1050807)", when="2025-11-05 10:30:00"):
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows), patch(
			f"{MODULE}.get_season_for_date", return_value=season
		) as season_for_date:
			result = resolve_rst_tp_details(tp_no, party, when)
		if when:
			season_for_date.assert_called_once_with(when)
		return result

	def test_key_is_pass_unique_key_of_transit_pass(self):
		res = self._resolve([self.KHARIF], "Kharif 2025")
		self.assertEqual(res["tp_status"], "TP Received")
		self.assertEqual(res["season_code"], "K25")
		self.assertEqual(res["rst_unique_key"], self.KHARIF["pass_unique_key"])
		self.assertEqual(res["key_message"], "")

	def test_season_of_rst_date_time_picks_between_two_passes(self):
		"""Real data: TP 18 + G S DUNGURIPALI exists in Kharif 2025 and Rabi 2025."""
		kharif = self._resolve([self.KHARIF, self.RABI], "Kharif 2025")
		rabi = self._resolve([self.KHARIF, self.RABI], "Rabi 2025")
		self.assertEqual(kharif["rst_unique_key"], self.KHARIF["pass_unique_key"])
		self.assertEqual(rabi["rst_unique_key"], self.RABI["pass_unique_key"])
		self.assertEqual((kharif["validation_message"], rabi["validation_message"]), ("", ""))

	def test_two_passes_without_season_still_blocked(self):
		res = self._resolve([self.KHARIF, self.RABI], None)
		self.assertIn("More than one", res["validation_message"])
		self.assertEqual(res["rst_unique_key"], "")

	def test_pass_in_other_season_leaves_key_empty(self):
		res = self._resolve([self.KHARIF], "Rabi 2025")
		self.assertEqual(res["tp_status"], "TP Received")
		self.assertEqual(res["season_code"], "R25")
		self.assertEqual(res["rst_unique_key"], "")
		self.assertIn("is not in season R25", res["key_message"])

	def test_no_season_gives_season_not_configured(self):
		res = self._resolve([self.KHARIF], None)
		self.assertEqual(res["tp_status"], "TP Received")
		self.assertEqual((res["season_code"], res["rst_unique_key"]), ("", ""))
		self.assertIn("No Season Master covers the RST Date & Time", res["key_message"])

	def test_no_transit_pass_no_key_but_season_code_set(self):
		for tp_no, rows in (("", []), ("18", [])):  # TP No Not Received / PPC Mismatch
			with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=True):
				res = self._resolve(rows, "Kharif 2025", tp_no=tp_no)
			self.assertEqual(res["season_code"], "K25")
			self.assertEqual((res["rst_unique_key"], res["key_message"]), ("", ""))

	def _doc(self, has_field=True):
		doc = RSTDetails.__new__(RSTDetails)
		doc.meta = MagicMock()  # meta is a cached_property, so this skips the database
		doc.meta.has_field.return_value = has_field
		doc.season_code, doc.rst_unique_key = "OLD", "OLD"
		return doc

	def test_save_stores_season_code_and_key(self):
		doc = self._doc()
		doc._set_season_code_and_rst_unique_key({"season_code": "K25", "rst_unique_key": "KEY", "key_message": ""})
		self.assertEqual((doc.season_code, doc.rst_unique_key), ("K25", "KEY"))
		self.msgprint.assert_not_called()

	def test_save_without_season_shows_season_not_configured(self):
		doc = self._doc()
		doc._set_season_code_and_rst_unique_key({"key_message": "No Season Master covers it."})
		self.assertEqual((doc.season_code, doc.rst_unique_key), ("", ""))
		self.assertEqual(self.msgprint.call_args.kwargs["title"], "Season Not Configured")

	def test_save_before_migrate_leaves_fields(self):
		doc = self._doc(has_field=False)
		doc._set_season_code_and_rst_unique_key({"season_code": "K25", "rst_unique_key": "KEY"})
		self.assertEqual((doc.season_code, doc.rst_unique_key), ("OLD", "OLD"))

	def test_weigh_bridge_uses_pass_of_rst_unique_key(self):
		doc = frappe._dict(tp_no="18", party_name="G S DUNGURIPALI(S1050807)", rst_unique_key=self.RABI["pass_unique_key"])
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=[self.KHARIF, self.RABI]):
			self.assertEqual(try_get_matching_transit_pass(doc).pass_unique_key, self.RABI["pass_unique_key"])

	def test_whitelist_passes_date_time(self):
		with patch(f"{MODULE}.resolve_rst_tp_details", return_value={}) as resolve:
			fetch_mill_and_agent_from_tp(tp_no=" 18 ", party_name="P", entry_datetime="2025-11-05 10:30:00")
			fetch_mill_and_agent_from_tp(tp_no="18", party_name="P", entry_datetime="")
		self.assertEqual(resolve.call_args_list[0].args, ("18", "P", "2025-11-05 10:30:00"))
		self.assertEqual(resolve.call_args_list[1].args, ("18", "P", None))


class TestRSTChhatniNoDB(unittest.TestCase):
	"""Hidden RST Chhatni fields (future RST-based entry): no site, no database."""

	def setUp(self):
		frappe.local.lang = "en"
		# flt(value, precision) reads the rounding method from System Settings; use Frappe's default.
		patcher = patch.object(frappe, "get_system_settings", MagicMock(return_value=None), create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def _doc(self, net=280, rate=4, tp_quantity=250, has_field=True):
		doc = RSTDetails.__new__(RSTDetails)
		doc.meta = MagicMock()  # meta is a cached_property, so this skips the database
		doc.meta.has_field.return_value = has_field
		doc.net_paddy_weight_qt, doc.chhatni_kg_per_qtl, doc.tp_quantity = net, rate, tp_quantity
		doc.chhatni_kg = doc.chhatni_qt = doc.received_chhatni_pct = "OLD"
		doc._set_chhatni()
		return (doc.chhatni_kg, doc.chhatni_qt, doc.received_chhatni_pct)

	def test_example_280_qt_at_4_kg_per_qtl_tp_250(self):
		self.assertEqual(self._doc(), (1120.0, 11.2, 4.48))

	def test_missing_or_zero_net_weight(self):
		for net in (0, None, -3):
			self.assertEqual(self._doc(net=net), (0.0, 0.0, 0.0))

	def test_missing_or_zero_tp_quantity_keeps_kg_and_qt(self):
		for tp_quantity in (0, None):
			self.assertEqual(self._doc(tp_quantity=tp_quantity), (1120.0, 11.2, 0.0))

	def test_missing_rate(self):
		self.assertEqual(self._doc(rate=None), (0.0, 0.0, 0.0))

	def test_skipped_before_migrate(self):
		self.assertEqual(self._doc(has_field=False), ("OLD", "OLD", "OLD"))

	def test_tp_quantity_only_for_tp_received(self):
		db = MagicMock()
		patches = [
			patch.object(frappe, "db", db, create=True),
			patch.object(frappe, "msgprint", MagicMock(), create=True),
			patch(f"{MODULE}.resolve_ppc_master_name", return_value=None),
			patch(f"{MODULE}.ppc_master_candidates", return_value=[]),
			patch(f"{MODULE}.party_matches_depo_master", return_value=False),
			patch(f"{MODULE}.get_agent_for_ppc_text", return_value=""),
			patch(f"{MODULE}.get_season_for_date", return_value=None),
		]
		for patcher in patches:
			patcher.start()
			self.addCleanup(patcher.stop)
		row = {"pass_unique_key": "M051007-X", "ppc": "AGALPUR(S1)", "miller": "", "quantity": 285.37}
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=[row]):
			received = resolve_rst_tp_details("342", "AGALPUR(S1)")
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=[]), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=True
		):
			mismatch = resolve_rst_tp_details("342", "WRONG")
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=True):
			no_tp = resolve_rst_tp_details("", "AGALPUR(S1)")
		self.assertEqual(received["tp_quantity"], 285.37)
		self.assertEqual((mismatch["tp_status"], mismatch["tp_quantity"]), ("PPC Mismatch", 0.0))
		self.assertEqual((no_tp["tp_status"], no_tp["tp_quantity"]), ("TP No Not Received", 0.0))


class TestRSTPPCNameAndCodeNoDB(unittest.TestCase):
	"""Party Name may be PPC name, code or name plus code, in any form: no site, no database."""

	ROW = {
		"pass_unique_key": "M051007-AGALPUR(S1050118)-K25-TP28",
		"transit_pass_no": "28",
		"ppc": "AGALPUR(S1050118)",
		"miller": "",
		"quantity": 250,
		"season": "Kharif(2025)",
	}

	MASTER = [
		frappe._dict(name="S1050118", code="S1050118", ppc_name="AGALPUR"),
		frappe._dict(name="S1050119", code="S1050119", ppc_name="BADAJEONA"),
		# Same PPC Name under two codes: name-only text is ambiguous.
		frappe._dict(name="MY200511", code="MY200511", ppc_name="TWIN"),
		frappe._dict(name="MY200512", code="MY200512", ppc_name="Twin"),
	]

	@staticmethod
	def _resolve_master(text):
		from ivri_od.procurement.transit_pass_resolve import ppc_master_candidates

		return (ppc_master_candidates(text) or [None])[0]

	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.db.get_value.return_value = ("AGALPUR", "S1050118")  # PPC Master ppc_name, code
		patchers = [
			patch.object(frappe, "db", self.db, create=True),
			patch.object(frappe, "msgprint", MagicMock(), create=True),
			patch.object(frappe, "get_system_settings", MagicMock(return_value=None), create=True),
			patch.object(frappe, "get_all", MagicMock(side_effect=lambda *a, **k: self.MASTER), create=True),
			patch(f"{MODULE}.resolve_ppc_master_name", side_effect=self._resolve_master),
			patch(f"{MODULE}.party_matches_depo_master", return_value=False),
			patch(f"{MODULE}.get_agent_for_ppc_text", return_value=""),
		]
		for patcher in patchers:
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_valid_ways_to_type_the_ppc_all_match(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import party_ppc_match_state as state

		for party in (
			"AGALPUR(S1050118)", "agalpur(s1050118)", "  Agalpur  ( S1050118 ) ",
			"AGALPUR S1050118", "AGALPUR(S1050118", "AGALPUR S1050118)", "AGALPUR", "agalpur", "S1050118", "s1050118",
		):
			self.assertEqual(state(party, "AGALPUR(S1050118)"), "match", party)
		# The pass text may be spelled differently; PPC Master still decides.
		self.assertEqual(state("AGALPUR(S1050118)", "Agalpur (s1050118)"), "match")

	def test_wrong_ppc_is_rejected(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import party_ppc_match_state as state

		for party in ("WRONG(S1050118)", "AGALPUR(S1050999)", "BADAJEONA", "S1050119", "AGALPURS", "", None):
			self.assertEqual(state(party, "AGALPUR(S1050118)"), "mismatch", party)
		self.assertEqual(state("AGALPUR", ""), "mismatch")

	def test_no_master_uses_pass_text(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import party_ppc_match_state as state

		self.assertEqual(state("NEWPPC(NP1)", "NEWPPC(NP1)"), "match")
		self.assertEqual(state("newppc np1", "NEWPPC(NP1)"), "match")
		self.assertEqual(state("NEWPPC(NP2)", "NEWPPC(NP1)"), "mismatch")
		self.assertEqual(state("NEWPPC(NP1)", "NEWPPC"), "mismatch")  # pass has no code to confirm it

	def test_name_that_fits_two_ppcs_is_ambiguous_but_name_with_code_is_not(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import party_ppc_match_state as state

		self.assertEqual(state("twin", "TWIN(MY200511)"), "ambiguous")
		self.assertEqual(state("TWIN(MY200511)", "TWIN(MY200511)"), "match")
		self.assertEqual(state("TWIN MY200512", "TWIN(MY200511)"), "mismatch")

	def _resolve(self, party, rows, tp_exists=True, tp_no="28"):
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=tp_exists
		):
			return resolve_rst_tp_details(tp_no, party)

	def test_tp_received_for_every_valid_input_with_canonical_party_name(self):
		for party in ("AGALPUR(S1050118)", "agalpur s1050118", "AGALPUR", "S1050118"):
			res = self._resolve(party, [self.ROW])
			self.assertEqual(res["tp_status"], "TP Received", party)
			self.assertEqual(res["party_name"], "AGALPUR(S1050118)", party)
		for party in ("WRONG(S1050118)", "AGALPUR(S1050999)", "BADAJEONA"):
			res = self._resolve(party, [self.ROW])
			self.assertEqual((res["tp_status"], res["mill_name"], res["party_name"]), ("PPC Mismatch", "", ""), party)
			self.assertEqual(res["notification"], "Enter Correct PPC Name.")

	def test_ambiguous_name_asks_for_clarification(self):
		row = dict(self.ROW, ppc="TWIN(MY200511)", pass_unique_key="M051007-TWIN(MY200511)-K25-TP28")
		res = self._resolve("twin", [row])
		self.assertEqual((res["tp_status"], res["mill_name"]), ("", ""))
		self.assertIn("more than one PPC", res["validation_message"])
		self.assertEqual(self._resolve("TWIN(MY200511)", [row])["tp_status"], "TP Received")


	def test_invalid_tp_keeps_priority(self):
		for party in ("AGALPUR", "AGALPUR(S1050118)", "WRONG"):
			self.assertEqual(self._resolve(party, [], tp_exists=False)["tp_status"], "Invalid TP No", party)

	def test_mismatch_is_saved_not_blocked(self):
		doc = RSTDetails.__new__(RSTDetails)
		doc.meta = MagicMock()  # meta is a cached_property, so this skips the database
		doc.tp_no, doc.party_name, doc.entry_datetime, doc.entry_date = "28", "BADAJEONA", None, None
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=[self.ROW]), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=True
		):
			doc._set_tp_status()
		self.assertEqual((doc.tp_status, doc.mill_name), ("PPC Mismatch", ""))

	def test_unique_key_uses_canonical_ppc_name_and_code(self):
		from ivri_od.procurement.doctype.rst_details.rst_details import rst_unique_key_for_pass

		self.assertEqual(rst_unique_key_for_pass(self.ROW, "28", "K25"), self.ROW["pass_unique_key"])
		odd_text = dict(self.ROW, ppc="Agalpur (s1050118)", pass_unique_key="M051007-Agalpur (s1050118)-K25-TP28")
		self.assertEqual(rst_unique_key_for_pass(odd_text, "28", "K25"), "M051007-AGALPUR(S1050118)-K25-TP28")

	def test_key_set_on_tp_received_in_season(self):
		with patch(f"{MODULE}.get_season_for_date", return_value="Kharif 2025"), patch(
			f"{MODULE}.get_season_code", return_value="K25"
		), patch(f"{MODULE}._transit_pass_matches_season", return_value=True), patch(
			f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=[self.ROW]
		):
			res = resolve_rst_tp_details("28", "AGALPUR(S1050118)", "2025-11-05 10:00:00")
		self.assertEqual(res["rst_unique_key"], "M051007-AGALPUR(S1050118)-K25-TP28")

	def test_weigh_bridge_pass_found_by_canonical_key(self):
		# Pass text spelled differently from PPC Master, so only the canonical key can find it.
		rabi = dict(self.ROW, ppc="Agalpur (s1050118)", season="Rabi(2025)", pass_unique_key="M051007-Agalpur (s1050118)-R25-TP28")
		doc = frappe._dict(tp_no="28", party_name="AGALPUR(S1050118)", rst_unique_key="M051007-AGALPUR(S1050118)-R25-TP28")
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=[self.ROW, rabi]):
			self.assertEqual(try_get_matching_transit_pass(doc).pass_unique_key, rabi["pass_unique_key"])


class TestRSTStatusLabelNoDB(unittest.TestCase):
	"""The status field shows as "Status"; its fieldname (and so the database column) stays tp_status."""

	def test_label_renamed_fieldname_unchanged(self):
		import json
		import os

		path = os.path.join(os.path.dirname(__file__), "rst_details.json")
		with open(path) as handle:
			fields = {field["fieldname"]: field for field in json.load(handle)["fields"]}
		self.assertEqual(fields["tp_status"]["label"], "Status")
		self.assertEqual(fields["tp_status"]["fieldtype"], "Data")
		self.assertEqual(fields["tp_status"].get("read_only"), 1)
		self.assertNotIn("TP Status", [field.get("label") for field in fields.values()])

	def test_script_never_shows_the_old_label(self):
		import os

		with open(os.path.join(os.path.dirname(__file__), "rst_details.js")) as handle:
			self.assertNotIn("TP Status", handle.read())


class TestRSTRiceDispatchNoDB(unittest.TestCase):
	"""Party Name equal to a Depo Master Depo Name -> Rice Dispatch; otherwise the old rules."""

	DEPOS = {"fci depot raipur"}  # lower-case Depo Names; the Depo Code is not part of the lookup

	def setUp(self):
		frappe.local.lang = "en"
		frappe.local._party_matches_any_transit_pass_ppc = {}

		def sql(query, values=(), **kwargs):
			if "tabDepo Master" not in query:
				return []
			self.queries.append(query)
			if values[0] in self.DEPOS:
				return [{"name": "RPR01", "code": "RPR01", "depo_name": "FCI Depot Raipur"}]
			return []

		self.queries = []
		self.db = MagicMock()
		self.db.sql.side_effect = sql
		self.msgprint = MagicMock()
		for name, value in (("db", self.db), ("msgprint", self.msgprint)):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		for target, kwargs in (
			("resolve_ppc_master_name", {"return_value": None}),
			("ppc_master_candidates", {"return_value": []}),
			("get_agent_for_ppc_text", {"return_value": ""}),
			("transit_pass_no_exists", {"return_value": False}),
			("find_transit_passes_by_tp_and_ppc", {"return_value": []}),
		):
			patcher = patch(f"{MODULE}.{target}", **kwargs)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_depo_name_gives_rice_dispatch(self):
		res = resolve_rst_tp_details("", "FCI Depot Raipur")
		self.assertEqual(res["tp_status"], "Rice Dispatch")
		self.assertEqual((res["mill_name"], res["agent_name"], res["notification"]), ("", "", ""))

	def test_match_ignores_case_and_extra_spaces(self):
		self.assertEqual(resolve_rst_tp_details("", "  fci   DEPOT  raipur ")["tp_status"], "Rice Dispatch")

	def test_lookup_uses_depo_name_only(self):
		resolve_rst_tp_details("", "FCI Depot Raipur")
		self.assertTrue(self.queries)
		for query in self.queries:
			self.assertIn("where lower(trim(depo_name)) = %s", query)
			self.assertNotIn("code =", query)

	def test_depo_code_alone_or_with_name_is_not_a_name_match(self):
		for party in ("RPR01", "FCI Depot Raipur (RPR01)"):
			self.assertNotEqual(resolve_rst_tp_details("", party)["tp_status"], "Rice Dispatch")

	def test_local_paddy_purchase_unchanged(self):
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=False):
			self.assertEqual(resolve_rst_tp_details("", "Some Farmer")["tp_status"], "Local Paddy Purchase")

	def test_government_paddy_purchase_unchanged(self):
		rows = [{"pass_unique_key": "M051007-AGALPUR(S1)-K25-TP1", "ppc": "AGALPUR(S1)", "miller": ""}]
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=True
		):
			self.assertEqual(resolve_rst_tp_details("TP1", "AGALPUR(S1)")["tp_status"], "TP Received")
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=True):
			self.assertEqual(resolve_rst_tp_details("", "AGALPUR(S1)")["tp_status"], "TP No Not Received")

	def test_invalid_tp_no_and_ppc_mismatch_unchanged(self):
		self.assertEqual(resolve_rst_tp_details("NOPE", "Unknown Party")["tp_status"], "Invalid TP No")
		with patch(f"{MODULE}.transit_pass_no_exists", return_value=True):
			self.assertEqual(resolve_rst_tp_details("TP1", "Unknown Party")["tp_status"], "PPC Mismatch")

	def test_empty_party_name_has_no_status_and_no_lookup(self):
		self.assertEqual(resolve_rst_tp_details("", "")["tp_status"], "")
		self.assertEqual(self.queries, [])

	def test_depo_name_with_empty_tp_no(self):
		doc = self._rst_doc("", "FCI Depot Raipur")
		doc._set_tp_status()
		self.assertEqual(doc.tp_status, "Rice Dispatch")
		self.assertEqual(doc.tp_no, "")

	def test_depo_name_with_lot_no_is_rice_dispatch_and_lot_no_is_kept_exactly(self):
		for lot_no in ("LOT-77/2026", " 342 ", "Lot  No 5", "TP-99"):
			doc = self._rst_doc(lot_no, "FCI Depot Raipur")
			doc._set_tp_status()
			self.assertEqual(doc.tp_status, "Rice Dispatch", lot_no)
			self.assertEqual(doc.tp_no, lot_no)
		self.msgprint.assert_not_called()

	def test_lot_no_is_not_validated_against_transit_pass_or_ppc(self):
		# Even if a Transit Pass lookup would fail, find several passes, or mismatch the PPC.
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc") as find, patch(
			f"{MODULE}.transit_pass_no_exists"
		) as exists, patch(f"{MODULE}.find_rst_transit_passes") as find_rst, patch(
			f"{MODULE}.party_matches_any_transit_pass_ppc"
		) as any_ppc:
			res = resolve_rst_tp_details("999-NOT-A-TP", "FCI Depot Raipur")
		for lookup in (find, exists, find_rst, any_ppc):
			lookup.assert_not_called()
		self.assertEqual(res["tp_status"], "Rice Dispatch")
		self.assertEqual((res["notification"], res["validation_message"], res["rst_unique_key"]), ("", "", ""))

	def test_depo_name_wins_over_a_matching_transit_pass(self):
		rows = [{"pass_unique_key": "M051007-X", "ppc": "FCI Depot Raipur", "miller": "", "quantity": 50}]
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=True
		):
			res = resolve_rst_tp_details("TP1", "FCI Depot Raipur")
		self.assertEqual((res["tp_status"], res["mill_name"], res["tp_quantity"]), ("Rice Dispatch", "", 0.0))

	def test_non_matching_name_keeps_all_tp_rules(self):
		rows = [{"pass_unique_key": "M051007-AGALPUR(S1)-K25-TP1", "ppc": "AGALPUR(S1)", "miller": ""}]
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows), patch(
			f"{MODULE}.transit_pass_no_exists", return_value=True
		):
			valid = resolve_rst_tp_details("TP1", "AGALPUR(S1)")
			mismatch = resolve_rst_tp_details("TP1", "Not A Depo")
		invalid = resolve_rst_tp_details("NOPE", "Not A Depo")  # find returns [], TP No does not exist
		self.assertEqual(valid["tp_status"], "TP Received")
		self.assertEqual(mismatch["tp_status"], "PPC Mismatch")
		self.assertEqual(invalid["tp_status"], "Invalid TP No")
		self.assertIn("Invalid TP No. NOPE", invalid["notification"])

	def test_depo_with_lot_no_equal_to_an_existing_transit_pass_no(self):
		"""Lot No 295 is also a real TP No of some PPC: it must still be a plain Lot No."""
		rows = [{"pass_unique_key": "M051007-BOBEYA(MY200703)-R25-TP295", "ppc": "BOBEYA(MY200703)",
			"miller": "SHREE", "quantity": 332.0, "transit_pass_no": "295"}]
		doc = self._rst_doc("295", "FCI Depot Raipur")
		with patch(f"{MODULE}.find_transit_passes_by_tp_and_ppc", return_value=rows) as find, patch(
			f"{MODULE}.transit_pass_no_exists", return_value=True
		) as exists, patch(f"{MODULE}.find_rst_transit_passes") as find_rst, patch(
			f"{MODULE}.try_get_matching_transit_pass"
		) as matching:
			doc._set_tp_status()
		for lookup in (find, exists, find_rst, matching):
			lookup.assert_not_called()
		self.assertEqual((doc.tp_status, doc.tp_no, doc.mill_name, doc.agent_name), ("Rice Dispatch", "295", "", ""))
		self.assertEqual(doc.tp_quantity, 0)

	def test_mill_check_does_not_apply_to_rice_dispatch(self):
		doc = self._rst_doc("LOT-1", "FCI Depot Raipur")
		doc._set_tp_status()
		doc._validate_mill_name()  # TP Received only: no "Missing Mill No" error

	def _rst_doc(self, tp_no, party_name):
		doc = RSTDetails.__new__(RSTDetails)
		doc.tp_no, doc.party_name, doc.tp_status = tp_no, party_name, "TP Received"
		doc.mill_name = doc.agent_name = "OLD"
		doc.entry_datetime = doc.entry_date = None
		doc.meta = MagicMock()
		return doc


class TestRSTRiceDispatchSeasonKeyNoDB(unittest.TestCase):
	"""Season Code from the RST Date & Time only; key DEPONAME(CODE)-K25-LOT{lot no}."""

	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.db.sql.return_value = [{"name": "RPR01", "code": "RPR01", "depo_name": "FCI Depot Raipur"}]
		for name, value in (("db", self.db), ("msgprint", MagicMock())):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		self.transit_pass_calls = []
		for target in (
			"find_transit_passes_by_tp_and_ppc",
			"transit_pass_no_exists",
			"_transit_pass_matches_season",
			"party_matches_any_transit_pass_ppc",
		):
			patcher = patch(f"{MODULE}.{target}", side_effect=lambda *a, _t=target, **k: self.transit_pass_calls.append(_t))
			patcher.start()
			self.addCleanup(patcher.stop)

	def _resolve(self, lot_no, season="Kharif 2025", season_code="K25", when="2025-11-05 10:30:00"):
		with patch(f"{MODULE}.get_season_for_date", return_value=season) as season_for, patch(
			f"{MODULE}.get_season_code", return_value=season_code
		):
			res = resolve_rst_tp_details(lot_no, "fci  DEPOT raipur", when)
		season_for.assert_called_once_with(when)
		return res

	def test_season_code_and_key_from_rst_date(self):
		res = self._resolve("77")
		self.assertEqual(res["tp_status"], "Rice Dispatch")
		self.assertEqual(res["season_code"], "K25")
		self.assertEqual(res["rst_unique_key"], "FCI Depot Raipur(RPR01)-K25-LOT77")
		self.assertEqual(res["key_message"], "")

	def test_rabi_season_gives_r_code(self):
		res = self._resolve("77", season="Rabi 2025", season_code="R25")
		self.assertEqual(res["rst_unique_key"], "FCI Depot Raipur(RPR01)-R25-LOT77")

	def test_lot_no_with_lot_prefix_or_slashes_and_empty_lot_no(self):
		self.assertEqual(self._resolve("LOT-77/2026")["rst_unique_key"], "FCI Depot Raipur(RPR01)-K25-LOT-77-2026")
		self.assertEqual(self._resolve("")["rst_unique_key"], "FCI Depot Raipur(RPR01)-K25")

	def test_no_matching_season_leaves_season_code_and_key_blank_with_the_usual_message(self):
		res = self._resolve("77", season=None, season_code="")
		self.assertEqual((res["season_code"], res["rst_unique_key"]), ("", ""))
		self.assertIn("No Season Master covers the RST Date & Time", res["key_message"])
		self.assertEqual(res["tp_status"], "Rice Dispatch")

	def test_season_never_taken_from_transit_pass_data(self):
		self._resolve("77")
		self._resolve("77", season=None, season_code="")
		self.assertEqual(self.transit_pass_calls, [])


class TestRSTRiceDispatchWeighBridgeNoDB(unittest.TestCase):
	"""Rice Dispatch RST -> Weigh Bridge Measurement: created once, updated on every later save."""

	WBM = "ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement"

	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.db.exists.side_effect = lambda doctype, name=None: bool(name)
		self.db.get_value.return_value = None
		self.get_doc = MagicMock()
		self.wbm = self.get_doc.return_value
		self.wbm.name = "WBM-2026-00001"
		self.status = MagicMock(return_value="Rice Dispatch")
		for patcher in (
			patch.object(frappe, "db", self.db, create=True),
			patch.object(frappe, "get_doc", self.get_doc, create=True),
			patch(f"{self.WBM}.compute_wbm_tp_status", self.status),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def _rst(self, **overrides):
		doc = RSTDetails.__new__(RSTDetails)
		values = dict(
			name="RST-0001", rst_no="R-1", tp_no="LOT-77/2026", party_name="  FCI Depot Raipur ",
			tp_status="Rice Dispatch", vehicle_no="cg04ab1234", gross_vehicle_weight_qt=40.0,
			tare_vehicle_weight_qt=15.0, deduction_qt=0.5, gunny_weight_qt=0, commodity="Paddy",
			entry_date="2026-10-23", entry_time="10:00:00", agent_name="OLD AGENT",
			local_purchase_order="", weigh_bridge_measurement="",
		)
		values.update(overrides)
		for key, value in values.items():
			setattr(doc, key, value)
		doc.db_set = MagicMock()
		return doc

	def _inserted(self):
		return self.get_doc.call_args.args[0]

	def test_creates_weigh_bridge_with_rice_dispatch_mapping(self):
		rst = self._rst()
		with patch(f"{MODULE}.try_get_matching_transit_pass") as matching, patch(
			f"{MODULE}.is_private_procurement_rst"
		) as private:
			rst._sync_weigh_bridge_measurement()
		matching.assert_not_called()
		private.assert_not_called()
		values = self._inserted()
		self.assertEqual(values["doctype"], "Weigh Bridge Measurement")
		expected = {
			"demo_rst_data": "RST-0001", "rst_no": "R-1", "party_name": "FCI Depot Raipur",
			"lot_no": "LOT-77/2026", "actual_truck_no": "CG04AB1234", "same_truck_as_transit_pass": 1,
			"is_farmer_or_agent": 0, "pass_unique_key": "", "agent_name": "", "vehicle_no": "",
			"load_weight": 40.0, "tare_weight": 15.0, "deduction": 0.5, "gunny_type": "Gunny Gross",
			"gunny_weight": 0, "commodity": "Paddy", "measurement_date": "2026-10-23",
			"measurement_time": "10:00:00", "tp_status": "Rice Dispatch",
		}
		for key, value in expected.items():
			self.assertEqual(values[key], value, key)
		self.assertNotIn("transit_pass_no", values)
		self.wbm.insert.assert_called_once()
		rst.db_set.assert_called_once_with("weigh_bridge_measurement", "WBM-2026-00001", update_modified=False)

	def test_gunny_cut_when_gunny_weight_entered(self):
		self._rst(gunny_weight_qt=0.3)._sync_weigh_bridge_measurement()
		self.assertEqual((self._inserted()["gunny_type"], self._inserted()["gunny_weight"]), ("Gunny Cut", 0.3))

	def test_lot_no_is_copied_exactly(self):
		self._rst(tp_no=" 007 ")._sync_weigh_bridge_measurement()
		self.assertEqual(self._inserted()["lot_no"], " 007 ")

	def test_repeated_save_updates_the_linked_record(self):
		rst = self._rst(weigh_bridge_measurement="WBM-2026-00001", tare_vehicle_weight_qt=16.5, tp_no="LOT-78")
		rst._sync_weigh_bridge_measurement()
		self.get_doc.assert_called_once_with("Weigh Bridge Measurement", "WBM-2026-00001")
		self.wbm.insert.assert_not_called()
		self.wbm.save.assert_called_once_with(ignore_permissions=True)
		sets = {call.args[0]: call.args[1] for call in self.wbm.set.call_args_list}
		self.assertEqual((sets["tare_weight"], sets["lot_no"]), (16.5, "LOT-78"))

	def test_lost_link_reuses_the_record_of_this_rst_instead_of_a_duplicate(self):
		self.db.get_value.return_value = "WBM-2026-00009"
		rst = self._rst(weigh_bridge_measurement="")
		rst._sync_weigh_bridge_measurement()
		self.db.get_value.assert_called_once_with("Weigh Bridge Measurement", {"demo_rst_data": "RST-0001"}, "name")
		self.get_doc.assert_called_once_with("Weigh Bridge Measurement", "WBM-2026-00009")
		self.wbm.insert.assert_not_called()
		rst.db_set.assert_called_once_with("weigh_bridge_measurement", "WBM-2026-00009", update_modified=False)

	def test_no_transit_pass_is_required_or_created(self):
		self._rst(tp_no="NOT-A-TP")._sync_weigh_bridge_measurement()
		self.assertEqual(self._inserted()["pass_unique_key"], "")
		self.assertNotIn("transit_pass_no", self._inserted())

	def test_weigh_bridge_side_clears_transit_pass_fields_and_keeps_lot_no(self):
		from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
			WeighBridgeMeasurement,
		)

		wbm = WeighBridgeMeasurement.__new__(WeighBridgeMeasurement)
		for key, value in dict(is_farmer_or_agent=1, pass_unique_key="K", transit_pass_no="9", tp_weight=5,
			truck_no_in_tp="X", pacs_name="P", vehicle_no="V", agent_name="A", party_name="", lot_no="").items():
			setattr(wbm, key, value)
		rst = frappe._dict(party_name=" FCI Depot Raipur ", tp_no="LOT-9", vehicle_no="cg04 ab 1234")
		with patch(f"{self.WBM}.normalize_vehicle_no", side_effect=lambda v: (v or "").replace(" ", "").upper()):
			wbm._apply_rst_rice_dispatch_mode(rst)
		self.assertEqual(
			(wbm.is_farmer_or_agent, wbm.pass_unique_key, wbm.transit_pass_no, wbm.tp_weight, wbm.truck_no_in_tp,
				wbm.pacs_name, wbm.vehicle_no, wbm.agent_name),
			(0, "", "", 0, "", "", "", ""),
		)
		self.assertEqual((wbm.party_name, wbm.lot_no, wbm.actual_truck_no), ("FCI Depot Raipur", "LOT-9", "CG04AB1234"))


class TestRiceDispatchNotLinkedToGRNNoDB(unittest.TestCase):
	"""Rice Dispatch weigh bridge records never create a GRN Note or feed Transit Pass totals."""

	WBM = "ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement"

	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		patcher = patch.object(frappe, "db", self.db, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_status_follows_the_rst(self):
		from ivri_od.procurement.doctype.weigh_bridge_measurement import weigh_bridge_measurement as m

		self.db.exists.return_value = True
		with patch.object(frappe, "get_doc", return_value=frappe._dict(tp_status="Rice Dispatch"), create=True):
			self.assertEqual(m.compute_wbm_tp_status(frappe._dict(demo_rst_data="RST-1")), "Rice Dispatch")

	def test_is_rice_dispatch_wbm(self):
		from ivri_od.procurement.doctype.weigh_bridge_measurement import weigh_bridge_measurement as m

		for status, expected in (("Rice Dispatch", True), ("TP Received", False), ("Local Procurement", False), ("", False)):
			self.db.get_value.return_value = status
			self.assertEqual(m.is_rice_dispatch_wbm("WBM-1"), expected, status)
		self.assertFalse(m.is_rice_dispatch_wbm(""))

	def test_no_grn_note_is_created_for_rice_dispatch(self):
		from ivri_od.procurement.doctype.weigh_bridge_measurement import weigh_bridge_measurement as m

		self.db.exists.return_value = True
		self.db.get_value.return_value = "Rice Dispatch"
		with patch("ivri_od.procurement.doctype.grn_note.grn_note.build_auto_grn_doc_dict") as build, patch(
			"ivri_od.procurement.doctype.grn_note.grn_note.sync_grn_from_weigh_bridge"
		) as sync, patch.object(m, "wbm_vehicle_has_exited", return_value=True), patch.object(
			m, "is_local_procurement_wbm", return_value=False
		), patch.object(frappe, "get_doc", create=True) as get_doc:
			m._ensure_grn_note_for_weigh_bridge("WBM-1")
		build.assert_not_called()
		sync.assert_not_called()
		get_doc.assert_not_called()

	def test_no_transit_pass_rollup_for_rice_dispatch(self):
		from ivri_od.procurement.doctype.weigh_bridge_measurement import weigh_bridge_measurement as m

		wbm = m.WeighBridgeMeasurement.__new__(m.WeighBridgeMeasurement)
		wbm.is_farmer_or_agent, wbm.tp_status, wbm.pass_unique_key = 0, "Rice Dispatch", "M1-X-K25-TP1"
		self.db.after_commit = MagicMock()
		wbm._schedule_procurement_rollup_sync()
		self.db.after_commit.assert_not_called()

	def test_grn_pending_reason_explains_rice_dispatch(self):
		from ivri_od.procurement.doctype.weigh_bridge_measurement import weigh_bridge_measurement as m

		self.db.exists.side_effect = lambda doctype, filters=None: doctype == "Weigh Bridge Measurement"
		self.db.get_value.return_value = "Rice Dispatch"
		self.assertEqual(m.grn_pending_reasons_for_wbm("WBM-1"), ["Rice Dispatch is not linked to a GRN Note."])


class TestRSTRegressionSyncNoDB(unittest.TestCase):
	"""Non-depo RST records keep their Weigh Bridge sync exactly as before."""

	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.db.exists.side_effect = lambda doctype, name=None: False
		self.db.sql.return_value = []
		self.get_doc = MagicMock()
		self.get_doc.return_value.name = "WBM-1"
		for patcher in (
			patch.object(frappe, "db", self.db, create=True),
			patch.object(frappe, "get_doc", self.get_doc, create=True),
			patch(
				"ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement.compute_wbm_tp_status",
				return_value="X",
			),
			patch(f"{MODULE}.party_matches_depo_master", return_value=False),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def _rst(self, tp_status, tp_no, party):
		doc = RSTDetails.__new__(RSTDetails)
		for key, value in dict(
			name="RST-1", rst_no="R-1", tp_no=tp_no, party_name=party, tp_status=tp_status, vehicle_no="cg04ab1234",
			gross_vehicle_weight_qt=40, tare_vehicle_weight_qt=15, deduction_qt=0, gunny_weight_qt=0,
			commodity="Paddy", entry_date="2026-10-23", entry_time="10:00:00", agent_name="AG",
			local_purchase_order="", weigh_bridge_measurement="",
		).items():
			setattr(doc, key, value)
		doc.db_set = MagicMock()
		return doc

	def test_local_paddy_purchase_still_creates_a_private_weigh_bridge(self):
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=False):
			self._rst("Local Paddy Purchase", "", "Some Farmer")._sync_weigh_bridge_measurement()
		values = self.get_doc.call_args.args[0]
		self.assertEqual((values["is_farmer_or_agent"], values["party_name"], values["actual_truck_no"]), (1, "Some Farmer", "CG04AB1234"))
		self.assertNotIn("lot_no", values)

	def test_tp_no_not_received_still_creates_a_weigh_bridge_without_pass(self):
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=True):
			self._rst("TP No Not Received", "", "AGALPUR(S1)")._sync_weigh_bridge_measurement()
		values = self.get_doc.call_args.args[0]
		self.assertEqual((values["is_farmer_or_agent"], values["pass_unique_key"], values["same_truck_as_transit_pass"]), (0, "", 1))
		self.assertNotIn("lot_no", values)

	def test_tp_received_still_links_the_transit_pass(self):
		tp = frappe._dict(pass_unique_key="M051007-AGALPUR(S1)-K25-TP1")
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=False), patch(
			f"{MODULE}.try_get_matching_transit_pass", return_value=tp
		):
			self._rst("TP Received", "1", "AGALPUR(S1)")._sync_weigh_bridge_measurement()
		values = self.get_doc.call_args.args[0]
		self.assertEqual(values["pass_unique_key"], "M051007-AGALPUR(S1)-K25-TP1")
		self.assertNotIn("lot_no", values)

	def test_invalid_tp_no_still_creates_nothing(self):
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=False), patch(
			f"{MODULE}.try_get_matching_transit_pass", return_value=None
		):
			self._rst("Invalid TP No", "9", "Whoever")._sync_weigh_bridge_measurement()
		self.get_doc.assert_not_called()

	def test_ppc_mismatch_creates_a_weigh_bridge_without_pass(self):
		"""PPC Mismatch records must also be listed in Weigh Bridge Measurement."""
		with patch(f"{MODULE}.party_matches_any_transit_pass_ppc", return_value=False), patch(
			f"{MODULE}.try_get_matching_transit_pass", return_value=None
		):
			self._rst("PPC Mismatch", "9", "Whoever")._sync_weigh_bridge_measurement()
		values = self.get_doc.call_args.args[0]
		self.assertEqual((values["pass_unique_key"], values["party_name"], values["is_farmer_or_agent"]), ("", "Whoever", 0))


class TestRSTDetailsTPLogic(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Ensure a known transit pass exists for testing
		cls.tp_no = "TEST-TP-99"
		cls.ppc_name = "TEST-PPC(S99999)"
		cls.key = "M051007-TEST-PPC(S99999)-K25-TEST-TP-99"

		if not frappe.db.exists("PPAS Transit Pass", cls.key):
			doc = frappe.get_doc(
				{
					"doctype": "PPAS Transit Pass",
					"pass_unique_key": cls.key,
					"transit_pass_no": cls.tp_no,
					"ppc": cls.ppc_name,
					"miller": "SHREE SHYAMJI PADDY PROCESSING PVT LTD(M051007)",
					"season": "Kharif 2025",
					"quantity": 100,
				}
			)
			doc.flags.ignore_mandatory = True
			doc.insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		if frappe.db.exists("PPAS Transit Pass", cls.key):
			frappe.delete_doc("PPAS Transit Pass", cls.key, ignore_permissions=True)
		super().tearDownClass()

	def test_rule_1_tp_exists_and_ppc_matches(self):
		"""1. TP No. exists in Transit Pass and Party Name matches its PPC name and code -> status TP Received."""
		# Exact match
		res = resolve_rst_tp_details(self.tp_no, self.ppc_name)
		self.assertEqual(res["tp_status"], "TP Received")
		self.assertEqual(res["mill_name"], "M051007")

		# With spaces that should be trimmed
		res_trimmed = resolve_rst_tp_details(f"  {self.tp_no}  ", f"  {self.ppc_name}  ")
		self.assertEqual(res_trimmed["tp_status"], "TP Received")

		# Name or code alone is a PPC Mismatch: both must match.
		for party in ("TEST-PPC", "S99999"):
			res_part = resolve_rst_tp_details(self.tp_no, party)
			self.assertEqual(res_part["tp_status"], "PPC Mismatch", party)

	def test_rule_2_tp_empty_party_matches_ppc(self):
		"""2. TP No. is empty but Party Name matches any Transit Pass PPC -> status TP No Not Received."""
		res = resolve_rst_tp_details("", self.ppc_name)
		self.assertEqual(res["tp_status"], "TP No Not Received")

		# Whitespace only TP No
		res_spaces = resolve_rst_tp_details("   ", f"  {self.ppc_name}  ")
		self.assertEqual(res_spaces["tp_status"], "TP No Not Received")

	def test_rule_3_tp_exists_ppc_mismatch(self):
		"""3. TP No. exists but its Transit Pass PPC does not match Party Name -> status PPC Mismatch."""
		res = resolve_rst_tp_details(self.tp_no, "DIFFERENT PPC NAME")
		self.assertNotEqual(res["tp_status"], "TP Received")
		self.assertEqual(res["tp_status"], "PPC Mismatch")
		self.assertEqual(res["notification"], "Enter Correct PPC Name.")

		# Wrong name with the right code must not be TP Received.
		res_code = resolve_rst_tp_details(self.tp_no, "DIFFERENT PPC NAME(S99999)")
		self.assertEqual(res_code["tp_status"], "PPC Mismatch")
		self.assertEqual(res_code["notification"], "Enter Correct PPC Name.")

	def test_rule_4_tp_empty_party_matches_no_ppc(self):
		"""4. TP No. is empty and Party Name matches no Transit Pass PPC -> status Local Paddy Purchase."""
		res = resolve_rst_tp_details("", "Completely Random Farmer Name")
		self.assertEqual(res["tp_status"], "Local Paddy Purchase")

		# With spaces
		res_spaces = resolve_rst_tp_details("   ", "   Local Paddy Vendor   ")
		self.assertEqual(res_spaces["tp_status"], "Local Paddy Purchase")

	def test_rule_5_tp_entered_not_found(self):
		"""5. TP No. is entered but not found in Transit Pass -> status Invalid TP No."""
		res = resolve_rst_tp_details("NONEXISTENT-TP-12345", self.ppc_name)
		self.assertNotEqual(res["tp_status"], "TP Received")
		self.assertEqual(res["tp_status"], "Invalid TP No")
		self.assertIn("Invalid TP No.", res["notification"])

	def test_fetch_mill_and_agent_whitelist_api(self):
		"""Test the whitelisted method used by client script."""
		res1 = fetch_mill_and_agent_from_tp(tp_no=self.tp_no, party_name=self.ppc_name)
		self.assertEqual(res1["tp_status"], "TP Received")

		res2 = fetch_mill_and_agent_from_tp(tp_no="", party_name=self.ppc_name)
		self.assertEqual(res2["tp_status"], "TP No Not Received")

		res3 = fetch_mill_and_agent_from_tp(tp_no=self.tp_no, party_name="WRONG")
		self.assertEqual(res3["notification"], "Enter Correct PPC Name.")
		self.assertEqual(res3["tp_status"], "PPC Mismatch")

		res4 = fetch_mill_and_agent_from_tp(tp_no="", party_name="Farmer")
		self.assertEqual(res4["tp_status"], "Local Paddy Purchase")

		res5 = fetch_mill_and_agent_from_tp(tp_no="999999", party_name=self.ppc_name)
		self.assertEqual(res5["tp_status"], "Invalid TP No")
		self.assertIn("Invalid TP No.", res5["notification"])
		self.assertNotEqual(res5["tp_status"], "TP Received")

	def test_rst_document_lifecycle(self):
		"""Test full RST Details document validation and saving."""
		rst_no = "RST-TEST-AUTOTEST-01"
		if frappe.db.exists("RST Details", rst_no):
			frappe.delete_doc("RST Details", rst_no, force=True, ignore_permissions=True)

		doc = frappe.new_doc("RST Details")
		doc.rst_no = rst_no
		doc.party_name = self.ppc_name
		doc.tp_no = self.tp_no
		doc.gross_vehicle_weight_qt = 50
		doc.tare_vehicle_weight_qt = 10
		doc.insert(ignore_permissions=True)

		self.assertEqual(doc.tp_status, "TP Received")
		self.assertEqual(doc.mill_name, "M051007")

		# Update TP No to empty -> status should update to TP No Not Received
		doc.tp_no = ""
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.tp_status, "TP No Not Received")

		# Cleanup
		frappe.delete_doc("RST Details", rst_no, force=True, ignore_permissions=True)

	def test_rst_document_saves_ppc_mismatch_and_invalid_tp_no(self):
		"""A mismatched PPC or an unknown TP No is saved with its status, never blocked."""
		rst_no = "RST-TEST-STATUS-03"
		cases = (
			(self.tp_no, "DIFFERENT PPC NAME", "PPC Mismatch"),
			("NONEXISTENT-TP-12345", self.ppc_name, "Invalid TP No"),
		)
		for tp_no, party_name, expected in cases:
			if frappe.db.exists("RST Details", {"rst_no": rst_no}):
				frappe.delete_doc("RST Details", rst_no, force=True, ignore_permissions=True)
			doc = frappe.new_doc("RST Details")
			doc.rst_no = rst_no
			doc.party_name = party_name
			doc.tp_no = tp_no
			doc.insert(ignore_permissions=True)
			self.assertEqual(doc.tp_status, expected)
			self.assertEqual(doc.mill_name, "")

			# Correcting the field recalculates the status on save.
			doc.tp_no, doc.party_name = self.tp_no, self.ppc_name
			doc.save(ignore_permissions=True)
			self.assertEqual(doc.tp_status, "TP Received")
			frappe.delete_doc("RST Details", doc.name, force=True, ignore_permissions=True)

	def test_rst_local_paddy_purchase_document(self):
		"""Test saving RST Details with Local Paddy Purchase status."""
		rst_no = "RST-LOCAL-AUTOTEST-02"
		if frappe.db.exists("RST Details", rst_no):
			frappe.delete_doc("RST Details", rst_no, force=True, ignore_permissions=True)

		doc = frappe.new_doc("RST Details")
		doc.rst_no = rst_no
		doc.party_name = "Independent Local Farmer"
		doc.tp_no = ""
		doc.gross_vehicle_weight_qt = 30
		doc.tare_vehicle_weight_qt = 10
		doc.insert(ignore_permissions=True)

		self.assertEqual(doc.tp_status, "Local Paddy Purchase")
		self.assertEqual(doc.mill_name, "")
		self.assertEqual(doc.agent_name, "")

		# Cleanup
		frappe.delete_doc("RST Details", rst_no, force=True, ignore_permissions=True)
