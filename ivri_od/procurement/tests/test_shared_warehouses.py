# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""One shared physical warehouse per location; Raw and Boiled share it.

The legal Company owns the warehouse and its accounting. The operating unit that owns stock in it is kept on the
Batch (Batch Operating Unit), on the Stock Entry and on the Bag Ledger, so stock and bags of each unit stay apart.
Mocked tests: no site, no database.
"""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement import inventory_foundation as inv
from ivri_od.procurement import stock_posting as sp
from ivri_od.procurement.report.stock_by_physical_location import stock_by_physical_location as report
from ivri_od.procurement.tests import test_inventory_foundation as base
from ivri_od.procurement.tests import test_stock_posting as posting_base

ORIGINAL_OWNERSHIP = inv.warehouse_ownership  # captured before the test cases patch it
MODULE = base.MODULE
SSPP, RGFP = base.SSPP, base.RGFP
BOILED, RAW = "M051007", "M050414"

SHARED_GODOWN = base.wh("GODOWN - SSPP", None, "SSPP GODOWN", unit_type=None)
SHARED_GALI = base.wh("GALI - SSPP", None, "SSPP GALI", unit_type=None)
SHARED_RGFP = base.wh("MAIN GODOWN - RGFP", None, "RGFP MAIN GODOWN", company=RGFP, unit_type=None)
SHARED = {w.name: w for w in (SHARED_GODOWN, SHARED_GALI, SHARED_RGFP)}
# every batch carries the operating unit that owns it; "B-NOUNIT" has none
BATCH_UNITS = {"B-K25": BOILED, "B-K25-2": RAW, "B-U1": BOILED, "B-R26": BOILED}
UNIT_TYPES = {BOILED: "BOILED", RAW: "RAW"}


class SharedCase(base.FoundationTestCase):
	def setUp(self):
		super().setUp()
		base.WAREHOUSES.update(SHARED)
		self.addCleanup(lambda: [base.WAREHOUSES.pop(name, None) for name in SHARED])
		extra_seasons = {"B-NOUNIT": "Kharif 2025", "B-U1": "Kharif 2025"}
		base.SEASONS.update(extra_seasons)
		self.addCleanup(lambda: [base.SEASONS.pop(name, None) for name in extra_seasons])
		for patcher in (
			patch(f"{MODULE}.batch_unit_column", return_value=True),
			patch(f"{MODULE}._batch_unit", side_effect=lambda b: BATCH_UNITS.get(b, "")),
			patch(f"{MODULE}._unit_type", side_effect=lambda u: UNIT_TYPES.get(u, "")),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.db.get_value.return_value = SSPP  # Mill Master accounting_company

	def moved(self, purpose="Material Receipt", src=None, tgt=None, batch="B-K25", **extra):
		return base.entry(purpose, [base.row(1, "Paddy", src=src, tgt=tgt, batch=batch)], **extra)


class TestWarehouseOwnership(unittest.TestCase):
	def setUp(self):
		self.db = MagicMock()
		patcher = patch.object(frappe, "db", self.db, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def ownership(self, **row):
		def get_value(doctype, name, fields=None, **k):
			if doctype == "Warehouse":
				if not row.get("exists", True):
					return None
				return frappe._dict(name="W", company=SSPP, operating_unit=row.get("operating_unit"), physical_location=row.get("physical_location"))
			return "BOILED"  # Mill Master type

		self.db.get_value.side_effect = get_value
		return ORIGINAL_OWNERSHIP("W")

	def test_a_physical_warehouse_without_a_unit_is_shared(self):
		info = self.ownership(operating_unit="", physical_location="SSPP GODOWN")
		self.assertEqual((info.operating_unit, info.unit_type, info.physical_location), (None, None, "SSPP GODOWN"))

	def test_a_per_unit_warehouse_still_names_its_unit_and_type(self):
		info = self.ownership(operating_unit=BOILED, physical_location="SSPP GODOWN")
		self.assertEqual((info.operating_unit, info.unit_type), (BOILED, "BOILED"))

	def test_a_warehouse_mapped_to_nothing_is_not_an_inventory_warehouse(self):
		self.assertIsNone(self.ownership(operating_unit="", physical_location=""))
		self.assertIsNone(self.ownership(operating_unit=None, physical_location=None))

	def test_an_unknown_warehouse_is_none(self):
		self.assertIsNone(self.ownership(exists=False))
		self.assertIsNone(ORIGINAL_OWNERSHIP(""))


class TestReceiptsIntoSharedWarehouses(SharedCase):
	def test_a_government_receipt_for_a_unit_goes_to_the_shared_warehouse_of_its_company(self):
		self.check(self.moved(tgt="GODOWN - SSPP", operating_unit=BOILED, grn_note="GRN-1"))

	def test_the_other_legal_company_shared_warehouse_is_refused(self):
		self.refuses(self.moved(tgt="MAIN GODOWN - RGFP", operating_unit=BOILED, grn_note="GRN-1"))

	def test_a_per_unit_warehouse_of_another_unit_is_refused_but_its_own_is_accepted(self):
		self.refuses(self.moved(tgt="GODOWN Raw - SSPP", operating_unit=BOILED, grn_note="GRN-1", batch="B-K25-2"))
		self.check(self.moved(tgt="GODOWN Boiled - SSPP", operating_unit=BOILED, grn_note="GRN-1"))

	def test_raw_and_boiled_receipts_use_the_same_warehouse(self):
		self.check(self.moved(tgt="GODOWN - SSPP", operating_unit=BOILED, grn_note="G1", batch="B-K25"))
		self.db.get_value.return_value = SSPP  # the Raw unit accounts to the same legal Company
		self.check(self.moved(tgt="GODOWN - SSPP", operating_unit=RAW, grn_note="G2", batch="B-K25-2"))


class TestBatchOwnsTheStock(SharedCase):
	def test_stock_in_a_shared_warehouse_needs_a_batch_with_an_operating_unit(self):
		self.refuses(self.moved(tgt="GODOWN - SSPP", batch="B-NOUNIT"))

	def test_without_the_batch_unit_field_nothing_can_go_into_a_shared_warehouse(self):
		with patch(f"{MODULE}.batch_unit_column", return_value=False):
			self.refuses(self.moved(tgt="GODOWN - SSPP"))

	def test_a_per_unit_warehouse_does_not_need_a_batch_unit(self):
		self.check(self.moved(tgt="GODOWN Boiled - SSPP", batch="B-NOUNIT"))

	def test_an_issue_out_of_a_shared_warehouse_also_needs_the_batch_unit(self):
		self.refuses(self.moved("Material Issue", src="GODOWN - SSPP", batch="B-NOUNIT"))
		self.check(self.moved("Material Issue", src="GODOWN - SSPP", batch="B-K25"))


class TestTransfersBetweenSharedWarehouses(SharedCase):
	def transfer(self, kind, src, tgt, batch="B-K25", **extra):
		return self.moved("Material Transfer", src=src, tgt=tgt, batch=batch, transfer_kind=kind, **extra)

	def test_a_physical_transfer_to_another_place_of_the_same_company_is_allowed(self):
		self.check(self.transfer(inv.PHYSICAL, "GODOWN - SSPP", "GALI - SSPP"))

	def test_it_must_change_the_place_and_keep_the_company(self):
		self.refuses(self.transfer(inv.PHYSICAL, "GODOWN - SSPP", "GODOWN - SSPP"))
		self.refuses(self.transfer(inv.PHYSICAL, "GODOWN - SSPP", "MAIN GODOWN - RGFP"))

	def test_a_per_unit_warehouse_to_a_shared_one_keeps_the_owner_only_if_the_batch_unit_agrees(self):
		self.check(self.transfer(inv.PHYSICAL, "GODOWN Boiled - SSPP", "GALI - SSPP", batch="B-K25"))  # batch is Boiled's
		self.refuses(self.transfer(inv.PHYSICAL, "GODOWN Boiled - SSPP", "GALI - SSPP", batch="B-K25-2"))  # batch is Raw's

	def test_changing_the_owning_unit_of_stock_in_a_shared_warehouse_is_not_set_up(self):
		self.refuses(self.transfer(inv.OWNERSHIP, "GODOWN - SSPP", "GODOWN - SSPP", ownership_transfer_reason="x"))
		self.refuses(self.transfer(inv.OWNERSHIP, "GODOWN Raw - SSPP", "GODOWN - SSPP", ownership_transfer_reason="x"))


class TestRiceInSharedWarehouses(SharedCase):
	def rice(self, item, unit):
		return base.entry(
			"Material Receipt", [base.row(1, item, tgt="GODOWN - SSPP", batch="B-K25")], operating_unit=unit
		)

	def test_rice_follows_the_operating_unit_of_the_stock_entry(self):
		self.check(self.rice("Boiled Rice", BOILED))
		self.check(self.rice("Raw Rice", RAW))
		self.refuses(self.rice("Raw Rice", BOILED))
		self.refuses(self.rice("Boiled Rice", RAW))

	def test_the_stock_entry_must_name_the_unit_for_rice_in_a_shared_warehouse(self):
		self.refuses(self.rice("Boiled Rice", ""))


class TestProductionInSharedWarehouses(SharedCase):
	def production(self, unit, produced_batch="B-U1", consumed_batch="B-K25"):
		return base.entry(
			"Manufacture",
			[
				base.row(1, "Paddy", src="GODOWN - SSPP", batch=consumed_batch),
				base.row(2, "Boiled Rice", tgt="GALI - SSPP", batch=produced_batch),
			],
			operating_unit=unit,
		)

	def test_one_unit_consumes_and_produces_in_shared_warehouses(self):
		self.check(self.production(BOILED))

	def test_the_unit_of_the_batches_and_of_the_entry_must_be_one(self):
		self.refuses(self.production(RAW))  # Boiled batches under a Raw entry

	def test_two_units_in_one_production_entry_are_refused(self):
		self.refuses(self.production(BOILED, consumed_batch="B-K25-2"))  # Raw paddy, Boiled rice

	def test_the_entry_must_name_the_unit_when_a_batch_does_not(self):
		with patch(f"{MODULE}._batch_unit", return_value=""):
			self.refuses(self.production(""))


class TestBagsStaySeparatePerUnitInASharedWarehouse(SharedCase):
	def setUp(self):
		super().setUp()
		patcher = patch(f"{MODULE}._government_paddy_item", return_value="Paddy")
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_the_bag_entry_belongs_to_the_unit_of_the_batch_and_the_company_of_the_warehouse(self):
		doc = base.entry("Material Receipt", [base.row(1, "Paddy", tgt="GODOWN - SSPP", batch="B-K25", bags=100)])
		entry = inv.bag_entries(doc)[0]
		self.assertEqual((entry["operating_unit"], entry["warehouse"], entry["company"], entry["bags"]), (BOILED, "GODOWN - SSPP", SSPP, 100))

	def test_another_unit_in_the_same_warehouse_gets_its_own_entry(self):
		doc = base.entry("Material Receipt", [base.row(1, "Paddy", tgt="GODOWN - SSPP", batch="B-K25-2", bags=40)])
		self.assertEqual(inv.bag_entries(doc)[0]["operating_unit"], RAW)

	def test_bags_of_one_unit_cannot_be_taken_against_the_other_units_balance(self):
		held = {("GODOWN - SSPP", "Paddy", "B-K25"): 100, ("GODOWN - SSPP", "Paddy", "B-K25-2"): 10}
		with patch(f"{MODULE}.bag_balance", side_effect=lambda w, i, b, lock=False: held.get((w, i, b), 0)):
			doc = base.entry("Material Issue", [base.row(1, "Paddy", src="GODOWN - SSPP", batch="B-K25-2", bags=30)])
			with self.assertRaises(frappe.ValidationError):  # the warehouse holds 110, the Raw batch only 10
				inv.check_bag_balance_before_submit(doc)
			ok = base.entry("Material Issue", [base.row(1, "Paddy", src="GODOWN - SSPP", batch="B-K25", bags=30)])
			inv.check_bag_balance_before_submit(ok)


class TestUnitLockStillSeesStockInSharedWarehouses(SharedCase):
	def test_a_unit_with_a_submitted_stock_entry_counts_as_having_stock(self):
		with patch.object(frappe, "get_all", MagicMock(return_value=[]), create=True):
			self.db.exists.return_value = True
			self.assertTrue(inv._unit_has_stock(BOILED))
			self.assertEqual(self.db.exists.call_args.args, ("Stock Entry", {"operating_unit": BOILED, "docstatus": 1}))

	def test_a_unit_with_no_stock_anywhere_has_none(self):
		with patch.object(frappe, "get_all", MagicMock(return_value=[]), create=True):
			self.db.exists.return_value = False
			self.assertFalse(inv._unit_has_stock(BOILED))


class TestStockReportOwnerWise(unittest.TestCase):
	def setUp(self):
		# flt(x, 3) reads the rounding method from System Settings; no site is bound, so use the default
		patcher = patch.object(frappe, "get_system_settings", lambda key: None, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def rows(self, **kwargs):
		warehouses = [frappe._dict(name="GODOWN - SSPP", company=SSPP, operating_unit=None, physical_location="SSPP GODOWN")]
		balances = [
			{"warehouse": "GODOWN - SSPP", "item_code": "Paddy", "batch_no": "B-BOILED", "qty": 70.0},
			{"warehouse": "GODOWN - SSPP", "item_code": "Paddy", "batch_no": "B-RAW", "qty": 30.0},
		]
		items = {"Paddy": {"stock_uom": "Quintal"}}
		return report.build_rows(
			warehouses, balances, items, {"B-BOILED": "Kharif 2025", "B-RAW": "Kharif 2025"},
			{("GODOWN - SSPP", "Paddy", "B-BOILED"): 140, ("GODOWN - SSPP", "Paddy", "B-RAW"): 60},
			UNIT_TYPES, kwargs.get("filters", {}), kwargs.get("batch_unit", {"B-BOILED": BOILED, "B-RAW": RAW}),
		)

	def test_one_shared_warehouse_shows_each_unit_and_the_combined_total(self):
		rows = self.rows()
		owners = {r["operating_unit"]: (r["qty"], r["bags"], r["unit_type"]) for r in rows if not r.get("is_combined")}
		self.assertEqual(owners, {BOILED: (70.0, 140, "BOILED"), RAW: (30.0, 60, "RAW")})
		combined = next(r for r in rows if r.get("is_combined"))
		self.assertEqual((combined["qty"], combined["bags"]), (100.0, 200))

	def test_the_unit_filter_keeps_only_that_units_batches(self):
		rows = self.rows(filters={"operating_unit": RAW})
		self.assertEqual([(r["operating_unit"], r["qty"]) for r in rows if not r.get("is_combined")], [(RAW, 30.0)])
		self.assertEqual(next(r for r in rows if r.get("is_combined"))["qty"], 30.0)

	def test_a_batch_without_a_unit_is_shown_as_unattributed_not_hidden(self):
		rows = self.rows(batch_unit={"B-BOILED": BOILED})
		self.assertIn(report.UNATTRIBUTED, {r["operating_unit"] for r in rows})
		self.assertEqual(next(r for r in rows if r.get("is_combined"))["qty"], 100.0)

	def test_an_older_per_unit_warehouse_is_still_owner_wise_by_its_own_unit(self):
		rows = report.build_rows(
			[frappe._dict(name="GODOWN Boiled - SSPP", company=SSPP, operating_unit=BOILED, physical_location="SSPP GODOWN")],
			[{"warehouse": "GODOWN Boiled - SSPP", "item_code": "Paddy", "batch_no": "B-BOILED", "qty": 5.0}],
			{"Paddy": {"stock_uom": "Quintal"}}, {"B-BOILED": "Kharif 2025"}, {}, UNIT_TYPES, {}, {},
		)
		self.assertEqual(rows[0]["operating_unit"], BOILED)


class TestPostingToTheSharedWarehouse(posting_base.StockPostingTestCase):
	SHARED_WH = frappe._dict(
		name="GODOWN - SSPP", company="Shree Shyamji Paddy Processing Pvt Ltd", is_group=0, disabled=0,
		is_rejected_warehouse=0, operating_unit=None, physical_location="SSPP GODOWN",
	)

	def errors(self, warehouse):
		return sp.grn_posting_errors(posting_base.grn(), frappe._dict(posting_base.WBM), posting_base.MILL, posting_base.ITEM, warehouse)

	def test_the_shared_warehouse_of_the_units_company_is_eligible(self):
		self.assertEqual(self.errors(self.SHARED_WH), [])
		self.assertEqual(self.errors(frappe._dict(self.SHARED_WH, operating_unit="")), [])

	def test_another_legal_companys_shared_warehouse_is_refused(self):
		self.assertTrue(self.errors(frappe._dict(self.SHARED_WH, company="Radhe Govind Food Products")))

	def test_a_per_unit_warehouse_of_another_unit_is_refused_and_the_message_names_both(self):
		errors = self.errors(frappe._dict(self.SHARED_WH, operating_unit="M050414"))
		self.assertTrue(any("M050414" in e and "M051007" in e for e in errors))

	def test_the_units_own_older_warehouse_is_still_eligible(self):
		self.assertEqual(self.errors(frappe._dict(self.SHARED_WH, operating_unit="M051007")), [])

	def test_a_warehouse_mapped_to_neither_a_unit_nor_a_location_is_refused(self):
		errors = self.errors(frappe._dict(self.SHARED_WH, physical_location=None, operating_unit=None))
		self.assertTrue(any("not mapped to a physical location" in e for e in errors))


class TestBatchCarriesTheUnit(posting_base.StockPostingTestCase):
	def setUp(self):
		super().setUp()
		self.grn = posting_base.grn()
		self.new_batches = []
		patcher = patch(f"{posting_base.MODULE}.batch_unit_column", return_value=True)
		patcher.start()
		self.addCleanup(patcher.stop)
		get_doc = MagicMock(side_effect=lambda spec: self.new_batches.append(spec) or MagicMock())
		patcher = patch.object(frappe, "get_doc", get_doc, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_the_unit_is_part_of_the_batch_id_and_stored_on_the_batch(self):
		self.db.exists.return_value = False
		batch_id = sp._ensure_batch("Paddy", "Kharif 2025", self.grn, "M051007")
		self.assertEqual(batch_id, "Kharif 2025-GOV-MOTA-M051007")
		self.assertEqual(self.new_batches[0]["operating_unit"], "M051007")
		self.assertEqual(self.new_batches[0]["batch_id"], batch_id)

	def test_raw_and_boiled_paddy_of_one_season_and_quality_get_different_batches(self):
		self.db.exists.return_value = False
		boiled = sp._ensure_batch("Paddy", "Kharif 2025", self.grn, "M051007")
		raw = sp._ensure_batch("Paddy", "Kharif 2025", self.grn, "M050414")
		self.assertNotEqual(boiled, raw)

	def test_an_existing_batch_of_the_same_unit_is_reused(self):
		self.db.exists.return_value = True
		self.db.get_value.return_value = frappe._dict(item="Paddy", season="Kharif 2025", procurement_type="Government", operating_unit="M051007")
		self.assertEqual(sp._ensure_batch("Paddy", "Kharif 2025", self.grn, "M051007"), "Kharif 2025-GOV-MOTA-M051007")
		self.assertEqual(self.new_batches, [])

	def test_an_existing_batch_of_another_unit_is_refused(self):
		self.db.exists.return_value = True
		self.db.get_value.return_value = frappe._dict(item="Paddy", season="Kharif 2025", procurement_type="Government", operating_unit="M050414")
		with self.assertRaises(frappe.ValidationError):
			sp._ensure_batch("Paddy", "Kharif 2025", self.grn, "M051007")

	def test_before_the_batch_unit_field_exists_no_unit_value_is_written(self):
		self.db.exists.return_value = False
		with patch(f"{posting_base.MODULE}.batch_unit_column", return_value=False):
			sp._ensure_batch("Paddy", "Kharif 2025", self.grn, "M051007")
		self.assertNotIn("operating_unit", self.new_batches[0])

	def test_posting_passes_the_units_code_to_the_batch(self):
		settings = frappe._dict(enabled=1, government_paddy_item="Paddy")
		se = MagicMock(name="se")
		se.name = "STE-1"
		se.flags = frappe._dict()
		self.db.get_value.return_value = "GRN-2026-00001"
		ensure = MagicMock(return_value="B")
		with patch.object(frappe, "only_for", MagicMock(), create=True), patch.object(frappe, "new_doc", MagicMock(return_value=se), create=True), \
			patch.object(frappe, "session", frappe._dict(user="u"), create=True), patch(f"{posting_base.MODULE}._settings", return_value=settings), \
			patch(f"{posting_base.MODULE}._load_context", return_value=(posting_base.grn(), posting_base.WBM, posting_base.MILL, posting_base.ITEM, TestPostingToTheSharedWarehouse.SHARED_WH, settings)), \
			patch(f"{posting_base.MODULE}.resolve_season_master_name", return_value="Kharif 2025"), \
			patch(f"{posting_base.MODULE}._ensure_batch", ensure), patch(f"{posting_base.MODULE}.get_active_posting", return_value=None):
			sp.post_grn_to_stock("GRN-2026-00001", "GODOWN - SSPP")
		self.assertEqual(ensure.call_args.args[3], "M051007")
		self.assertEqual(se.operating_unit, "M051007")  # the owning unit is on the Stock Entry too


class TestWarehouseRules(posting_base.StockPostingTestCase):
	"""validate_warehouse for the shared warehouse and for the older per-unit one."""

	def setUp(self):
		super().setUp()
		self.place = frappe._dict(company=SSPP, is_active=1, shared_with_other_companies=0)
		self.clash = None
		self.clash_filters = None

		def get_value(doctype, filters=None, fieldname=None, *a, **k):
			if doctype == "Physical Location":
				return self.place
			if doctype == "Warehouse":
				self.clash_filters = filters
				return self.clash
			return SSPP  # Mill Master accounting company

		self.db.get_value.side_effect = get_value
		self.db.exists.return_value = True

	def doc(self, **values):
		doc = {"name": "GODOWN - SSPP", "company": SSPP, "physical_location": "SSPP GODOWN", "operating_unit": None, "is_group": 0, "disabled": 0}
		doc.update(values)
		return frappe._dict(doc)

	def test_a_shared_warehouse_needs_no_operating_unit(self):
		sp.validate_warehouse(self.doc())
		sp.validate_warehouse(self.doc(operating_unit=""))

	def test_a_warehouse_with_neither_unit_nor_location_is_left_alone(self):
		sp.validate_warehouse(frappe._dict(name="Stores - SSPP", company=SSPP, operating_unit=None, physical_location=None, is_group=0))

	def test_the_location_must_belong_to_the_warehouse_company(self):
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(frappe._dict(self.doc(), company="Radhe Govind Food Products"))

	def test_the_location_must_exist_and_be_active(self):
		self.place = None
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc())
		self.place = frappe._dict(company=SSPP, is_active=0, shared_with_other_companies=0)
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc())

	def test_a_second_shared_warehouse_for_the_same_location_and_company_is_refused(self):
		self.clash = "OLD GODOWN - SSPP"
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc())
		self.assertEqual(self.clash_filters["physical_location"], "SSPP GODOWN")
		self.assertEqual(self.clash_filters["operating_unit"], ["is", "not set"])
		self.assertEqual(self.clash_filters["company"], SSPP)

	def test_the_shared_check_does_not_count_the_warehouse_itself_or_a_disabled_one(self):
		sp.validate_warehouse(self.doc())
		self.assertEqual(self.clash_filters["name"], ["!=", "GODOWN - SSPP"])
		self.assertEqual(self.clash_filters["disabled"], 0)
		self.clash = "X"  # a clash exists, but a disabled warehouse is never checked against it
		sp.validate_warehouse(frappe._dict(self.doc(), disabled=1))

	def test_a_group_warehouse_is_not_checked_for_a_location(self):
		sp.validate_warehouse(frappe._dict(self.doc(), is_group=1, physical_location=None, operating_unit=None))

	def test_the_older_per_unit_rule_is_unchanged(self):
		self.clash = "GODOWN Boiled - SSPP"
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(frappe._dict(self.doc(), operating_unit="M051007"))
		self.assertEqual(self.clash_filters["operating_unit"], "M051007")


if __name__ == "__main__":
	unittest.main()
