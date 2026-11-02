# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Government paddy receipt posting. Mocked tests: no site, no database."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement import stock_posting as sp

MODULE = "ivri_od.procurement.stock_posting"


def _throw(msg, *args, **kwargs):
	raise frappe.ValidationError(msg)


KEY = "M051007-BAKTI(S1050104)-K25-TP45"


def grn(**overrides):
	values = frappe._dict(
		name="GRN-2026-00001", is_local_procurement=0, pass_unique_key="M051007-BAKTI(S1050104)-K25-TP45",
		qc_decision="Accepted", net_weight=123.456, weigh_bridge_measurement="WBM-2026-00001",
		mill_name="SHREE SHYAMJI PADDY PROCESSING PVT LTD(M051007)", no_of_bags=250, total_bags=240, cmr_season="Kharif 2025",
		receipt_datetime=None, ppc="BAKTI(S1050104)", transit_pass_no="45", paddy_quality="Mota",
		tp_rows=[frappe._dict(name=KEY, pass_unique_key=KEY, transit_pass_no="45")],
	)
	values.update(overrides)
	return values


# Transit Pass says 250 bags (GRN no_of_bags); 240 were counted (total_bags). Only the counted bags are physical.
WBM = frappe._dict(
	name="WBM-2026-00001", quality_test="Accepted", tare_weight=18.2, net_weight=123.456,
	total_bags=240, qc_received_bags=240, qc_returned_bags=0, shared_with=[], pass_unique_key=KEY,
)
MILL = frappe._dict(name="M051007", is_active=1, accounting_company="Shree Shyamji Paddy Processing Pvt Ltd")
ITEM = frappe._dict(name="Paddy", disabled=0, is_stock_item=1, has_batch_no=1, stock_uom="Quintal")
WAREHOUSE = frappe._dict(
	name="GODOWN Boiled - SSPP", company="Shree Shyamji Paddy Processing Pvt Ltd", is_group=0, disabled=0,
	is_rejected_warehouse=0, operating_unit="M051007",
)


class StockPostingTestCase(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		# flt(x, 3) reads the rounding method from System Settings; no site is bound, so use the default.
		for name, value in (
			("throw", _throw),
			("db", self.db),
			("msgprint", MagicMock()),
			("get_system_settings", lambda key: None),
		):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)


class TestQuantity(StockPostingTestCase):
	def test_quintal_item_uses_net_weight_unchanged(self):
		self.assertEqual(sp.convert_to_stock_qty(123.456, "Quintal"), 123.456)

	def test_kg_item_converts_once(self):
		self.assertEqual(sp.convert_to_stock_qty(1.5, "Kg"), 150.0)

	def test_other_uom_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			sp.convert_to_stock_qty(1, "Tonne")


class TestEligibility(StockPostingTestCase):
	def errors(self, g=None, wbm=WBM, mill=MILL, item=ITEM, warehouse=WAREHOUSE):
		return sp.grn_posting_errors(g or grn(), wbm, mill, item, warehouse)

	def test_accepted_government_grn_is_eligible(self):
		self.assertEqual(self.errors(), [])

	def test_local_purchase_is_refused(self):
		self.assertTrue(self.errors(grn(is_local_procurement=1)))

	def test_rejected_or_pending_is_refused(self):
		self.assertTrue(self.errors(grn(qc_decision="Pending QC")))
		self.assertTrue(self.errors(wbm=frappe._dict(WBM, quality_test="Rejected")))

	def test_missing_tare_or_zero_net_is_refused(self):
		self.assertTrue(self.errors(wbm=frappe._dict(WBM, tare_weight=0)))
		self.assertTrue(self.errors(g=grn(net_weight=0), wbm=frappe._dict(WBM, net_weight=0)))

	def test_grn_and_wbm_net_weight_must_match(self):
		self.assertTrue(self.errors(g=grn(net_weight=120)))

	def test_unit_without_accounting_company_is_refused(self):
		self.assertTrue(self.errors(mill=frappe._dict(MILL, accounting_company="")))

	def test_inactive_unit_is_refused(self):
		self.assertTrue(self.errors(mill=frappe._dict(MILL, is_active=0)))

	def test_item_must_be_batch_stock_item_in_quintal(self):
		self.assertTrue(self.errors(item=None))
		self.assertTrue(self.errors(item=frappe._dict(ITEM, has_batch_no=0)))
		self.assertTrue(self.errors(item=frappe._dict(ITEM, stock_uom="Tonne")))

	def test_warehouse_must_match_company_and_unit(self):
		self.assertTrue(self.errors(warehouse=frappe._dict(WAREHOUSE, company="Other Company")))
		self.assertTrue(self.errors(warehouse=frappe._dict(WAREHOUSE, operating_unit="M050414")))
		self.assertTrue(self.errors(warehouse=frappe._dict(WAREHOUSE, is_group=1)))
		self.assertTrue(self.errors(warehouse=frappe._dict(WAREHOUSE, is_rejected_warehouse=1)))


POSTED = frappe._dict(
	name="SPL-00001", stock_entry="STE-00001", net_weight_qt=123.456, pass_unique_key=grn().pass_unique_key,
	weigh_bridge_measurement="WBM-2026-00001", mill_name=grn().mill_name, qc_decision="Accepted", no_of_bags=240,
	is_local_procurement=0,
)


class TestFreeze(StockPostingTestCase):
	def test_unchanged_grn_has_no_differences(self):
		self.assertEqual(sp.snapshot_differences(grn(), POSTED), [])

	def test_changed_net_weight_bags_or_pass_are_found(self):
		self.assertTrue(sp.snapshot_differences(grn(net_weight=100), POSTED))
		self.assertTrue(sp.snapshot_differences(grn(total_bags=1), POSTED))  # physical bags are frozen
		self.assertEqual(sp.snapshot_differences(grn(no_of_bags=1), POSTED), [])  # the Transit Pass reference is not
		self.assertTrue(sp.snapshot_differences(grn(pass_unique_key="X"), POSTED))
		self.assertTrue(sp.snapshot_differences(grn(qc_decision="Pending QC"), POSTED))

	def test_guard_blocks_changed_grn_after_posting(self):
		with patch(f"{MODULE}.get_active_posting", return_value=POSTED):
			with self.assertRaises(frappe.ValidationError):
				sp.guard_grn_note(grn(net_weight=100))
			sp.guard_grn_note(grn())  # same values: other GRN updates (TP totals) still work

	def test_guard_ignores_unposted_grn(self):
		with patch(f"{MODULE}.get_active_posting", return_value=None):
			sp.guard_grn_note(grn(net_weight=1))

	def test_weigh_bridge_net_weight_frozen_after_posting(self):
		self.db.get_value.return_value = "GRN-2026-00001"
		wbm = frappe._dict(name="WBM-2026-00001", net_weight=100, total_bags=240)
		with patch(f"{MODULE}.get_active_posting", return_value=POSTED):
			with self.assertRaises(frappe.ValidationError):
				sp.guard_weigh_bridge(wbm)
			with self.assertRaises(frappe.ValidationError):  # a changed physical bag count is frozen too
				sp.guard_weigh_bridge(frappe._dict(wbm, net_weight=123.456, total_bags=200))
			sp.guard_weigh_bridge(frappe._dict(wbm, net_weight=123.456))

	def test_posted_grn_and_wbm_cannot_be_deleted(self):
		self.db.get_value.return_value = "GRN-2026-00001"
		with patch(f"{MODULE}.get_active_posting", return_value=POSTED):
			with self.assertRaises(frappe.ValidationError):
				sp.guard_grn_note_trash(grn())
			with self.assertRaises(frappe.ValidationError):
				sp.guard_weigh_bridge_trash(frappe._dict(name="WBM-2026-00001"))


def stock_entry(**overrides):
	row = frappe._dict(idx=1, s_warehouse=None, t_warehouse="GODOWN Boiled - SSPP", allow_zero_valuation_rate=1,
		basic_rate=0, transfer_qty=123.456, stock_uom="Quintal", no_of_bags=240)
	doc = MagicMock()
	doc.get.side_effect = lambda key, default=None: {"grn_note": "GRN-2026-00001"}.get(key, default)
	doc.grn_note = "GRN-2026-00001"
	doc.purpose = "Material Receipt"
	doc.items = [row]
	doc.flags = frappe._dict(from_grn_posting=True)
	for key, value in overrides.items():
		setattr(doc, key, value)
	return doc


class TestStockEntryRules(StockPostingTestCase):
	def setUp(self):
		super().setUp()
		self.db.get_value.return_value = frappe._dict(net_weight=123.456, total_bags=240)

	def test_plain_stock_entry_is_not_touched(self):
		doc = stock_entry()
		doc.get.side_effect = lambda key, default=None: default
		sp.validate_stock_entry(doc)

	def test_valid_receipt_passes(self):
		sp.validate_stock_entry(stock_entry())

	def test_hand_made_receipt_linked_to_grn_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			sp.validate_stock_entry(stock_entry(flags=frappe._dict()))

	def test_any_rate_is_refused(self):
		doc = stock_entry()
		doc.items[0].basic_rate = 25
		with self.assertRaises(frappe.ValidationError):
			sp.validate_stock_entry(doc)

	def test_missing_zero_flag_is_refused(self):
		doc = stock_entry()
		doc.items[0].allow_zero_valuation_rate = 0
		with self.assertRaises(frappe.ValidationError):
			sp.validate_stock_entry(doc)

	def test_quantity_must_equal_grn_net_weight(self):
		doc = stock_entry()
		doc.items[0].transfer_qty = 120
		with self.assertRaises(frappe.ValidationError):
			sp.validate_stock_entry(doc)

	def test_receipt_bags_must_equal_the_physical_count_not_the_transit_pass_count(self):
		doc = stock_entry()
		doc.items[0].no_of_bags = 250  # the Transit Pass figure
		with self.assertRaises(frappe.ValidationError):
			sp.validate_stock_entry(doc)

	def test_transfer_or_issue_rows_are_refused(self):
		doc = stock_entry()
		doc.items[0].s_warehouse = "Other - SSPP"
		with self.assertRaises(frappe.ValidationError):
			sp.validate_stock_entry(doc)

	def test_cancel_closes_the_posting_log(self):
		self.db.get_value.return_value = "SPL-00001"
		doc = stock_entry()
		doc.name = "STE-00001"
		doc.flags = frappe._dict(cancel_reason="Wrong godown")
		with patch.object(frappe, "session", frappe._dict(user="stock@example.com"), create=True):
			sp.on_cancel_stock_entry(doc)
		values = self.db.set_value.call_args[0][2]
		self.assertEqual(values["status"], "Cancelled")
		self.assertIsNone(values["active_key"])  # unique key freed: the GRN can be posted again
		self.assertEqual(values["cancel_reason"], "Wrong godown")


class TestPostGrnToStock(StockPostingTestCase):
	def setUp(self):
		super().setUp()
		self.settings = frappe._dict(enabled=1, government_paddy_item="Paddy")
		self.se = MagicMock()
		self.se.name = "STE-00001"
		self.se.flags = frappe._dict()
		self.db.get_value.return_value = "GRN-2026-00001"  # row lock
		self.log = MagicMock()
		patches = [
			patch.object(frappe, "only_for", MagicMock(), create=True),
			patch.object(frappe, "new_doc", MagicMock(return_value=self.se), create=True),
			patch.object(frappe, "get_doc", MagicMock(return_value=self.log), create=True),
			patch.object(frappe, "session", frappe._dict(user="stock@example.com"), create=True),
			patch(f"{MODULE}._settings", return_value=self.settings),
			patch(f"{MODULE}._load_context", return_value=(grn(), WBM, MILL, ITEM, WAREHOUSE, self.settings)),
			patch(f"{MODULE}.resolve_season_master_name", return_value="Kharif 2025"),
			patch(f"{MODULE}._ensure_batch", return_value="Kharif 2025-GOV-MOTA"),
			patch(f"{MODULE}.get_active_posting", return_value=None),
		]
		for patcher in patches:
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_posts_net_weight_unchanged_at_zero_rate(self):
		name = sp.post_grn_to_stock("GRN-2026-00001", "GODOWN Boiled - SSPP")
		self.assertEqual(name, "STE-00001")
		row = self.se.append.call_args[0][1]
		self.assertEqual(row["qty"], 123.456)  # GRN net_weight, not recalculated, no second deduction
		self.assertEqual(row["transfer_qty"], 123.456)
		self.assertEqual(row["no_of_bags"], 240)  # physical bags (total_bags), not the Transit Pass 250
		self.assertEqual(row["basic_rate"], 0)
		self.assertEqual(row["allow_zero_valuation_rate"], 1)
		self.assertEqual(row["batch_no"], "Kharif 2025-GOV-MOTA")
		self.assertEqual(self.se.company, MILL.accounting_company)
		self.assertEqual(self.se.purpose, "Material Receipt")
		self.assertTrue(self.se.flags.from_grn_posting)
		self.se.insert.assert_called_once()
		self.se.submit.assert_called_once()
		log = self.log_doc()
		self.assertEqual(log["active_key"], "GRN-2026-00001")
		self.assertEqual(log["net_weight_qt"], 123.456)
		self.assertEqual(log["no_of_bags"], 240)
		self.assertEqual(log["status"], "Posted")

	def log_doc(self):
		return frappe.get_doc.call_args[0][0]

	def test_local_grn_creates_no_stock_entry_no_log_and_no_bags(self):
		local = grn(is_local_procurement=1, pass_unique_key="", tp_rows=[])
		with patch(f"{MODULE}._load_context", return_value=(local, WBM, MILL, ITEM, WAREHOUSE, self.settings)):
			with self.assertRaises(frappe.ValidationError):
				sp.post_grn_to_stock("GRN-2026-00001", "GODOWN Boiled - SSPP")
		frappe.new_doc.assert_not_called()
		frappe.get_doc.assert_not_called()

	def test_unresolved_key_creates_nothing(self):
		bad = grn(tp_rows=[])
		with patch(f"{MODULE}._load_context", return_value=(bad, WBM, MILL, ITEM, WAREHOUSE, self.settings)):
			with self.assertRaises(frappe.ValidationError):
				sp.post_grn_to_stock("GRN-2026-00001", "GODOWN Boiled - SSPP")
		frappe.new_doc.assert_not_called()
		self.se.submit.assert_not_called()

	def test_second_posting_is_blocked(self):
		with patch(f"{MODULE}.get_active_posting", return_value=POSTED):
			with self.assertRaises(frappe.ValidationError):
				sp.post_grn_to_stock("GRN-2026-00001", "GODOWN Boiled - SSPP")
		self.se.submit.assert_not_called()

	def test_disabled_settings_block_posting(self):
		self.settings.enabled = 0
		with self.assertRaises(frappe.ValidationError):
			sp.post_grn_to_stock("GRN-2026-00001", "GODOWN Boiled - SSPP")

	def test_ineligible_grn_is_blocked_before_any_document_is_made(self):
		with patch(
			f"{MODULE}._load_context",
			return_value=(grn(qc_decision="Pending QC"), WBM, MILL, ITEM, WAREHOUSE, self.settings),
		):
			with self.assertRaises(frappe.ValidationError):
				sp.post_grn_to_stock("GRN-2026-00001", "GODOWN Boiled - SSPP")
		frappe.new_doc.assert_not_called()

	def test_unknown_season_is_blocked(self):
		with patch(f"{MODULE}.resolve_season_master_name", return_value=None):
			with self.assertRaises(frappe.ValidationError):
				sp.post_grn_to_stock("GRN-2026-00001", "GODOWN Boiled - SSPP")
		frappe.new_doc.assert_not_called()

	def test_cancel_needs_a_reason_and_an_active_posting(self):
		with self.assertRaises(frappe.ValidationError):
			sp.cancel_stock_posting("GRN-2026-00001", "  ")
		with self.assertRaises(frappe.ValidationError):
			sp.cancel_stock_posting("GRN-2026-00001", "Wrong godown")  # nothing posted


class TestPhysicalBags(StockPostingTestCase):
	"""The ledger counts physical bags (GRN Note.total_bags). The Transit Pass count is reference data only."""

	def errors(self, g=None, wbm=None):
		return sp.physical_bag_errors(g or grn(), wbm or frappe._dict(WBM))

	def test_clean_load_is_accepted_even_though_transit_pass_bags_differ(self):
		self.assertEqual(grn().no_of_bags, 250)
		self.assertEqual(grn().total_bags, 240)
		self.assertEqual(self.errors(), [])
		# a one-bag difference like WBM-2026-00097 (Transit Pass 426, counted 425) is not an error
		self.assertEqual(self.errors(grn(no_of_bags=426, total_bags=425), frappe._dict(WBM, total_bags=425, qc_received_bags=425)), [])

	def test_no_counted_bags_is_refused(self):
		self.assertTrue(self.errors(grn(total_bags=0), frappe._dict(WBM, total_bags=0, qc_received_bags=0)))

	def test_grn_and_weigh_bridge_bags_must_agree(self):
		self.assertTrue(self.errors(wbm=frappe._dict(WBM, total_bags=230)))

	def test_quality_check_count_must_agree_or_exist(self):
		self.assertTrue(self.errors(wbm=frappe._dict(WBM, qc_received_bags=196)))
		self.assertTrue(self.errors(wbm=frappe._dict(WBM, qc_received_bags=None)))

	def test_returned_bags_are_refused_because_the_kept_bags_are_not_established(self):
		self.assertTrue(self.errors(wbm=frappe._dict(WBM, qc_returned_bags=12)))

	def test_loads_sharing_one_quality_check_are_refused_with_a_clear_message(self):
		errors = self.errors(wbm=frappe._dict(WBM, shared_with=["WBM-2026-00104", "GRN-2026-00122"]))
		self.assertEqual(len(errors), 1)
		self.assertIn("WBM-2026-00104", errors[0])
		self.assertIn("twice", errors[0])

	def test_eligibility_includes_the_bag_rules(self):
		errors = sp.grn_posting_errors(grn(), frappe._dict(WBM, shared_with=["WBM-2026-00104"]), MILL, ITEM, WAREHOUSE)
		self.assertTrue(errors)
		self.assertEqual(sp.grn_posting_errors(grn(), frappe._dict(WBM), MILL, ITEM, WAREHOUSE), [])

	def test_sharing_is_found_by_quality_check_or_vehicle_visit(self):
		calls = []

		def get_all(doctype, **kwargs):
			calls.append((doctype, kwargs))
			return {"Weigh Bridge Measurement": ["WBM-2026-00104"], "GRN Note": ["GRN-2026-00122", "WBM-2026-00104"]}[doctype]

		with patch.object(frappe, "get_all", get_all, create=True):
			shared = sp._loads_sharing_qc("QC-2026-124", "GE-2026-00062", "WBM-2026-00103", "GRN-2026-00123")
		self.assertEqual(shared, ["GRN-2026-00122", "WBM-2026-00104"])
		wbm_call = next(kw for dt, kw in calls if dt == "Weigh Bridge Measurement")
		self.assertIn(["quality_check", "=", "QC-2026-124"], wbm_call["or_filters"])
		self.assertIn(["gate_entry", "=", "GE-2026-00062"], wbm_call["or_filters"])
		self.assertIn(["name", "!=", "WBM-2026-00103"], wbm_call["filters"])  # never counts itself

	def test_load_context_carries_the_qc_facts_and_sharing(self):
		g = grn(quality_check="QC-2026-124")
		g.name = "GRN-2026-00123"

		def get_value(doctype, filters=None, fieldname=None, *a, **k):
			if doctype == "Weigh Bridge Measurement":
				return frappe._dict(name="WBM-2026-00103", quality_test="Accepted", tare_weight=1, net_weight=71.188, total_bags=196, gate_entry="GE-2026-00062", pass_unique_key=KEY)
			if doctype == "Quality Check":
				return frappe._dict(paddy_received_in_pkt=196, paddy_returned=0, gate_entry="GE-2026-00062")
			return frappe._dict(name="x")

		self.db.get_value.side_effect = get_value
		tp = frappe._dict(name=g.pass_unique_key, pass_unique_key=g.pass_unique_key, transit_pass_no="45")
		with patch.object(frappe, "get_doc", MagicMock(return_value=g), create=True), patch.object(
			frappe, "get_all", MagicMock(return_value=[tp]), create=True
		), patch(
			f"{MODULE}._settings", return_value=frappe._dict(government_paddy_item="Paddy")
		), patch(f"{MODULE}.resolve_mill_master_name", return_value="M051007"), patch(
			f"{MODULE}._loads_sharing_qc", return_value=["WBM-2026-00104"]
		) as sharing:
			_grn, wbm, *_rest = sp._load_context("GRN-2026-00123", "GODOWN Boiled - SSPP")
		self.assertEqual((wbm.total_bags, wbm.qc_received_bags, wbm.qc_returned_bags), (196, 196, 0))
		self.assertEqual(wbm.shared_with, ["WBM-2026-00104"])
		sharing.assert_called_once_with("QC-2026-124", "GE-2026-00062", "WBM-2026-00103", "GRN-2026-00123")
		self.assertEqual([r.name for r in _grn.tp_rows], [KEY])  # the Transit Pass the key resolves to is loaded for validation

	def test_weigh_bridge_drift_includes_the_physical_bags(self):
		self.db.get_value.return_value = frappe._dict(net_weight=123.456, total_bags=230)
		changes = sp._drift(grn(), POSTED)
		self.assertTrue(any("Total Bags" in c for c in changes))


class TestGovernmentEligibility(StockPostingTestCase):
	"""Only a GRN Note whose Pass Unique Key resolves to its PPAS Transit Pass is a government receipt."""

	def errors(self, g=None, wbm=None):
		return sp.government_pass_errors(g or grn(), wbm if wbm is not None else frappe._dict(WBM))

	def test_valid_key_that_resolves_to_its_transit_pass_is_government(self):
		self.assertEqual(self.errors(), [])
		self.assertEqual(sp.grn_posting_errors(grn(), frappe._dict(WBM), MILL, ITEM, WAREHOUSE), [])

	def test_local_purchase_without_a_key_is_not_government_and_says_so(self):
		errors = self.errors(grn(is_local_procurement=1, pass_unique_key="", tp_rows=[]))
		self.assertEqual(len(errors), 1)
		self.assertIn("local paddy purchase", errors[0])
		self.assertTrue(sp.grn_posting_errors(grn(is_local_procurement=1, pass_unique_key="", tp_rows=[]), frappe._dict(WBM), MILL, ITEM, WAREHOUSE))

	def test_local_flag_together_with_a_key_is_inconsistent_not_government(self):
		errors = self.errors(grn(is_local_procurement=1))
		self.assertEqual(len(errors), 1)
		self.assertIn("inconsistent", errors[0])

	def test_missing_key_on_a_non_local_grn_is_refused(self):
		self.assertTrue(self.errors(grn(pass_unique_key="", tp_rows=[]), frappe._dict(WBM, pass_unique_key="")))

	def test_key_that_matches_no_transit_pass_is_refused_not_trusted(self):
		errors = self.errors(grn(tp_rows=[]))
		self.assertTrue(errors and "does not match any" in errors[0])

	def test_key_that_could_not_be_checked_is_refused(self):
		g = grn()
		g.pop("tp_rows")  # unresolved: never treated as valid
		errors = self.errors(g)
		self.assertEqual(len(errors), 1)
		self.assertIn("could not be checked", errors[0])

	def test_key_matching_several_transit_passes_is_ambiguous_and_refused(self):
		tp = frappe._dict(name=KEY, pass_unique_key=KEY, transit_pass_no="45")
		self.assertTrue(self.errors(grn(tp_rows=[tp, tp])))

	def test_key_that_only_matches_by_case_is_not_the_same_key(self):
		self.assertTrue(self.errors(grn(tp_rows=[frappe._dict(name=KEY.lower(), pass_unique_key=KEY.lower(), transit_pass_no="45")])))

	def test_transit_pass_number_must_agree(self):
		self.assertTrue(self.errors(grn(transit_pass_no="99")))

	def test_weigh_bridge_key_must_agree(self):
		self.assertTrue(self.errors(wbm=frappe._dict(WBM, pass_unique_key="OTHER-KEY")))

	def test_eligibility_is_decided_by_the_key_alone_not_by_supplier_item_warehouse_or_bags(self):
		# same key facts, wildly different bags / warehouse / item name: government status does not change
		g = grn(total_bags=7)
		w = frappe._dict(WBM, total_bags=7, qc_received_bags=7)
		self.assertEqual(sp.grn_posting_errors(g, w, MILL, frappe._dict(ITEM, name="Anything"), frappe._dict(WAREHOUSE, name="Elsewhere")), [])
		self.assertTrue(self.errors(grn(pass_unique_key="", tp_rows=[], total_bags=240, party_name="Government Supplier")))

	def test_one_transit_pass_may_feed_several_grns_when_their_loads_are_distinct(self):
		calls = []

		def get_all(doctype, **kwargs):
			calls.append((doctype, kwargs))
			return []  # no other weighment or GRN on this QC / vehicle visit

		with patch.object(frappe, "get_all", get_all, create=True):
			shared = sp._loads_sharing_qc("QC-2026-125", "GE-2026-00064", "WBM-2026-00105", "GRN-2026-00121")
		self.assertEqual(shared, [])
		self.assertFalse(any("pass_unique_key" in str(kw) for _dt, kw in calls))  # sharing a Transit Pass is not what is refused


class TestWarehouseRule(StockPostingTestCase):
	"""Company match of the unit. The full owner / place rules are in test_inventory_foundation."""

	def setUp(self):
		super().setUp()
		self.place = frappe._dict(company="Shree Shyamji Paddy Processing Pvt Ltd", is_active=1, shared_with_other_companies=0)

	def _db(self, unit_company):
		def get_value(doctype, filters=None, fieldname=None, *a, **k):
			return {"Mill Master": unit_company, "Physical Location": self.place}.get(doctype)

		self.db.get_value.side_effect = get_value
		self.db.exists.return_value = True

	def test_warehouse_company_must_match_unit_company(self):
		self._db("Shree Shyamji Paddy Processing Pvt Ltd")
		doc = frappe._dict(
			name="W1", operating_unit="M051007", company="Radhe Govind Food Products", physical_location="SSPP GODOWN", is_group=0
		)
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(doc)
		sp.validate_warehouse(frappe._dict(doc, company="Shree Shyamji Paddy Processing Pvt Ltd"))

	def test_unit_without_accounting_company_is_not_blocked_by_the_company_rule(self):
		self._db(None)
		sp.validate_warehouse(
			frappe._dict(name="W1", operating_unit="M051007", company="Shree Shyamji Paddy Processing Pvt Ltd",
				physical_location="SSPP GODOWN", is_group=0)
		)


if __name__ == "__main__":
	unittest.main()
