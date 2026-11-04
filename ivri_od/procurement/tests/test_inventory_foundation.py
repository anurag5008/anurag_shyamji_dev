# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Inventory foundation rules. Mocked tests: no site, no database."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement import inventory_foundation as inv
from ivri_od.procurement import stock_posting as sp
from ivri_od.procurement.doctype.stock_posting_settings.stock_posting_settings import StockPostingSettings
from ivri_od.procurement.report.stock_by_physical_location import stock_by_physical_location as report

MODULE = "ivri_od.procurement.inventory_foundation"
SSPP = "Shree Shyamji Paddy Processing Pvt Ltd"
RGFP = "Radhe Govind Food Products"


def _throw(msg, *args, **kwargs):
	raise frappe.ValidationError(msg)


def wh(name, unit, location, company=SSPP, unit_type="RAW"):
	return frappe._dict(name=name, company=company, operating_unit=unit, physical_location=location, unit_type=unit_type)


# Owner (unit) and place (location) are separate: SSPP Raw and SSPP Boiled share the SSPP GODOWN.
RAW_GODOWN = wh("GODOWN Raw - SSPP", "M050414", "SSPP GODOWN", unit_type="RAW")
BOILED_GODOWN = wh("GODOWN Boiled - SSPP", "M051007", "SSPP GODOWN", unit_type="BOILED")
RAW_GALI = wh("GALI Raw - SSPP", "M050414", "SSPP GALI", unit_type="RAW")
RGFP_RAW = wh("MAIN Raw - RGFP", "M050415", "RGFP MAIN GODOWN", company=RGFP, unit_type="RAW")
WAREHOUSES = {w.name: w for w in (RAW_GODOWN, BOILED_GODOWN, RAW_GALI, RGFP_RAW)}
SEASONS = {"B-K25": "Kharif 2025", "B-K25-2": "Kharif 2025", "B-R26": "Rabi 2026", "B-NONE": "", "B-LOCAL": "Kharif 2025", "B-UNTYPED": "Kharif 2025"}
PROCUREMENT = {"B-LOCAL": "Local", "B-UNTYPED": ""}  # every other batch used in these tests is Government
BATCH_ITEMS = {"Paddy", "Raw Rice", "Boiled Rice", "Bran"}


def row(idx=1, item="Paddy", src=None, tgt=None, batch="B-K25", bags=0, name=None):
	return frappe._dict(
		idx=idx, item_code=item, s_warehouse=src, t_warehouse=tgt, batch_no=batch, no_of_bags=bags,
		serial_and_batch_bundle="", name=name or f"row{idx}",
	)


def entry(purpose, rows, **extra):
	doc = frappe._dict(
		name="STE-00001", doctype="Stock Entry", purpose=purpose, items=rows, company=SSPP, posting_date="2026-10-27",
		add_to_transit=0, transfer_kind="", ownership_transfer_reason="", grn_note="", operating_unit="",
	)
	doc.update(extra)
	return doc


SETTINGS = frappe._dict(raw_rice_item="Raw Rice", boiled_rice_item="Boiled Rice", government_paddy_item="Paddy")


class FoundationTestCase(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		for name, value in (
			("throw", _throw), ("db", self.db), ("msgprint", MagicMock()),
			("get_system_settings", lambda key: None),
			("get_cached_doc", MagicMock(return_value=SETTINGS)),
		):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		for patcher in (
			patch(f"{MODULE}.warehouse_ownership", side_effect=lambda w: WAREHOUSES.get(w)),
			patch(f"{MODULE}._batch_season", side_effect=lambda b: SEASONS.get(b, "")),
			patch(f"{MODULE}._has_batch", side_effect=lambda i: i in BATCH_ITEMS),
			patch(f"{MODULE}._batch_procurement_type", side_effect=lambda b: PROCUREMENT.get(b, "Government") if b else ""),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def check(self, doc):
		inv.validate_stock_entry_foundation(doc)

	def refuses(self, doc):
		with self.assertRaises(frappe.ValidationError):
			inv.validate_stock_entry_foundation(doc)


class TestApprovedStructure(FoundationTestCase):
	def test_five_units_map_to_three_legal_companies(self):
		self.assertEqual(set(inv.APPROVED_UNITS), {"M050414", "M051007", "M050415", "M050410", "M050421"})
		companies = {inv.approved_company_for_unit(code) for code in inv.APPROVED_UNITS}
		self.assertEqual(companies, set(inv.LEGAL_COMPANIES.values()))
		self.assertEqual(inv.approved_company_for_unit("M051007"), SSPP)
		self.assertEqual(inv.approved_company_for_unit("M050410"), RGFP)
		self.assertEqual(inv.approved_company_for_unit("M050421"), "Laddu Gopal Industries")
		self.assertIsNone(inv.approved_company_for_unit("M999999"))

	def test_raw_boiled_types_are_as_approved(self):
		types = {code: spec["type"] for code, spec in inv.APPROVED_UNITS.items()}
		self.assertEqual(types, {"M050414": "RAW", "M051007": "BOILED", "M050415": "RAW", "M050410": "BOILED", "M050421": "BOILED"})

	def test_nine_distinct_physical_locations_two_gali_apart(self):
		names = inv.approved_location_names()
		self.assertEqual(len(names), 9)
		self.assertEqual(len(set(names)), 9)
		self.assertIn("SSPP GALI", names)
		self.assertIn("RGFP GALI", names)
		self.assertIn("LGI ECO STAND PLANT", names)

	def test_mill_master_must_use_the_approved_company(self):
		doc = MagicMock()
		doc.name = "M051007"
		doc.get.side_effect = lambda k, d=None: {"accounting_company": RGFP}.get(k, d)
		with self.assertRaises(frappe.ValidationError):
			inv.validate_mill_master_mapping(doc)

	def test_mill_master_with_right_or_empty_company_passes(self):
		for company in (SSPP, ""):
			doc = MagicMock()
			doc.name = "M051007"
			doc.get.side_effect = lambda k, d=None, c=company: {"accounting_company": c}.get(k, d)
			doc.get_doc_before_save.return_value = None
			inv.validate_mill_master_mapping(doc)

	def test_accounting_company_locked_once_unit_has_stock(self):
		doc = MagicMock()
		doc.name = "M051007"
		doc.get.side_effect = lambda k, d=None: {"accounting_company": SSPP}.get(k, d)
		doc.get_doc_before_save.return_value = frappe._dict(accounting_company="Another Company")
		with patch(f"{MODULE}._unit_has_stock", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				inv.validate_mill_master_mapping(doc)
		with patch(f"{MODULE}._unit_has_stock", return_value=False):
			inv.validate_mill_master_mapping(doc)


class TestWarehouseMapping(FoundationTestCase):
	"""Owner (operating unit) and place (physical location) are two separate links on the Warehouse."""

	def doc(self, **kw):
		values = dict(name="GODOWN Raw - SSPP", company=SSPP, operating_unit="M050414", physical_location="SSPP GODOWN", is_group=0)
		values.update(kw)
		return frappe._dict(values)

	def setup_db(self, unit_company=None, place=None, clash=None):
		place = place or frappe._dict(company=SSPP, is_active=1, shared_with_other_companies=0)

		def get_value(doctype, filters=None, fieldname=None, *a, **k):
			if doctype == "Mill Master":
				return unit_company
			if doctype == "Physical Location":
				return place
			if doctype == "Warehouse":
				return clash
			return None

		self.db.get_value.side_effect = get_value
		self.db.exists.return_value = True

	def test_warehouse_without_unit_is_left_alone(self):
		sp.validate_warehouse(self.doc(operating_unit="", physical_location=""))

	def test_location_without_owner_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc(operating_unit=""))

	def test_unit_without_location_is_refused(self):
		self.setup_db()
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc(physical_location=""))

	def test_valid_owner_and_place_pass(self):
		self.setup_db(unit_company=SSPP)
		sp.validate_warehouse(self.doc())

	def test_warehouse_company_must_match_unit_company(self):
		self.setup_db(unit_company=RGFP)
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc())

	def test_other_company_location_needs_the_shared_flag(self):
		self.setup_db(place=frappe._dict(company=RGFP, is_active=1, shared_with_other_companies=0))
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc())
		self.setup_db(place=frappe._dict(company=RGFP, is_active=1, shared_with_other_companies=1))
		sp.validate_warehouse(self.doc())

	def test_inactive_location_is_refused(self):
		self.setup_db(place=frappe._dict(company=SSPP, is_active=0, shared_with_other_companies=0))
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc())

	def test_second_warehouse_for_same_owner_and_place_is_refused(self):
		self.setup_db(clash="GODOWN Raw 2 - SSPP")
		with self.assertRaises(frappe.ValidationError):
			sp.validate_warehouse(self.doc())

	def test_two_owners_may_share_one_location(self):
		self.setup_db(unit_company=SSPP, clash=None)  # no other warehouse for this owner+place
		sp.validate_warehouse(self.doc(name="GODOWN Boiled - SSPP", operating_unit="M051007"))


class TestTransfers(FoundationTestCase):
	def test_entry_outside_unit_warehouses_is_not_touched(self):
		self.check(entry("Material Transfer", [row(src="Stores - X", tgt="Other - X")]))

	def test_transfer_needs_a_kind(self):
		self.refuses(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GALI Raw - SSPP")]))

	def test_physical_transfer_same_owner_new_place(self):
		self.check(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GALI Raw - SSPP")], transfer_kind=inv.PHYSICAL))

	def test_physical_transfer_cannot_change_owner(self):
		self.refuses(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GODOWN Boiled - SSPP")], transfer_kind=inv.PHYSICAL))

	def test_physical_transfer_cannot_stay_in_place(self):
		same_place = wh("GODOWN Raw 2 - SSPP", "M050414", "SSPP GODOWN")
		WAREHOUSES[same_place.name] = same_place
		self.addCleanup(WAREHOUSES.pop, same_place.name)
		self.refuses(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt=same_place.name)], transfer_kind=inv.PHYSICAL))

	def test_raw_paddy_to_boiled_unit_is_an_ownership_transfer_in_same_place(self):
		doc = entry(
			"Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GODOWN Boiled - SSPP")],
			transfer_kind=inv.OWNERSHIP, ownership_transfer_reason="Raw paddy sent for parboiling",
		)
		self.check(doc)

	def test_ownership_transfer_needs_a_reason(self):
		self.refuses(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GODOWN Boiled - SSPP")], transfer_kind=inv.OWNERSHIP))

	def test_ownership_transfer_cannot_move_the_stock(self):
		boiled_gali = wh("GALI Boiled - SSPP", "M051007", "SSPP GALI", unit_type="BOILED")
		WAREHOUSES[boiled_gali.name] = boiled_gali
		self.addCleanup(WAREHOUSES.pop, boiled_gali.name)
		self.refuses(entry(
			"Material Transfer", [row(src="GODOWN Raw - SSPP", tgt=boiled_gali.name)],
			transfer_kind=inv.OWNERSHIP, ownership_transfer_reason="x",
		))

	def test_ownership_transfer_must_change_owner(self):
		self.refuses(entry(
			"Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GODOWN Raw - SSPP")],
			transfer_kind=inv.OWNERSHIP, ownership_transfer_reason="x",
		))

	def test_ownership_transfer_between_legal_companies_is_not_allowed_yet(self):
		cross = wh("GODOWN RGFP Raw - RGFP", "M050415", "SSPP GODOWN", company=RGFP)
		WAREHOUSES[cross.name] = cross
		self.addCleanup(WAREHOUSES.pop, cross.name)
		self.refuses(entry(
			"Material Transfer", [row(src="GODOWN Raw - SSPP", tgt=cross.name)],
			transfer_kind=inv.OWNERSHIP, ownership_transfer_reason="x",
		))

	def test_transfer_to_unmapped_warehouse_is_refused(self):
		self.refuses(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="Stores - X")], transfer_kind=inv.PHYSICAL))

	def test_transit_transfer_is_refused(self):
		self.refuses(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GALI Raw - SSPP")], transfer_kind=inv.PHYSICAL, add_to_transit=1))


class TestSeasonAndProduction(FoundationTestCase):
	def test_batch_without_season_is_refused(self):
		self.refuses(entry("Material Receipt", [row(tgt="GODOWN Raw - SSPP", batch="B-NONE")]))

	def test_batch_with_season_is_accepted(self):
		self.check(entry("Material Receipt", [row(tgt="GODOWN Raw - SSPP", batch="B-K25")]))

	def test_transfer_with_seasonless_batch_is_refused(self):
		self.refuses(entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GALI Raw - SSPP", batch="B-NONE")], transfer_kind=inv.PHYSICAL))

	def production(self, consumed, produced, **extra):
		rows = [row(1, "Paddy", src="GODOWN Raw - SSPP", batch=consumed[0])]
		rows += [row(2 + i, "Paddy", src="GODOWN Raw - SSPP", batch=b) for i, b in enumerate(consumed[1:])]
		n = len(rows)
		rows += [row(n + 1 + i, item, tgt="GODOWN Raw - SSPP", batch=b) for i, (item, b) in enumerate(produced)]
		return entry("Manufacture", rows, **extra)

	def test_one_season_in_and_out_is_accepted(self):
		self.check(self.production(["B-K25"], [("Raw Rice", "B-K25-2"), ("Bran", "B-K25-2")]))

	def test_two_seasons_in_one_run_are_refused(self):
		self.refuses(self.production(["B-K25", "B-R26"], [("Raw Rice", "B-K25")]))

	def test_output_must_carry_the_input_season(self):
		self.refuses(self.production(["B-K25"], [("Raw Rice", "B-R26")]))

	def test_batch_must_be_chosen_not_auto_picked(self):
		self.refuses(self.production([""], [("Raw Rice", "B-K25")]))

	def test_one_operating_unit_per_production_entry(self):
		rows = [row(1, "Paddy", src="GODOWN Raw - SSPP"), row(2, "Raw Rice", tgt="GODOWN Boiled - SSPP", batch="B-K25")]
		self.refuses(entry("Manufacture", rows))

	def test_raw_rice_only_in_a_raw_unit(self):
		self.check(entry("Material Receipt", [row(item="Raw Rice", tgt="GODOWN Raw - SSPP")]))
		self.refuses(entry("Material Receipt", [row(item="Raw Rice", tgt="GODOWN Boiled - SSPP")]))

	def test_boiled_rice_only_in_a_boiled_unit(self):
		self.check(entry("Material Receipt", [row(item="Boiled Rice", tgt="GODOWN Boiled - SSPP")]))
		self.refuses(entry("Material Receipt", [row(item="Boiled Rice", tgt="GODOWN Raw - SSPP")]))

	def test_paddy_may_sit_in_raw_or_boiled_units(self):
		for target in ("GODOWN Raw - SSPP", "GODOWN Boiled - SSPP"):
			self.check(entry("Material Receipt", [row(item="Paddy", tgt=target)]))

	def test_grn_receipt_must_land_in_its_own_unit(self):
		doc = entry("Material Receipt", [row(tgt="GODOWN Boiled - SSPP")], grn_note="GRN-1", operating_unit="M050414")
		self.refuses(doc)
		doc = entry("Material Receipt", [row(tgt="GODOWN Raw - SSPP")], grn_note="GRN-1", operating_unit="M050414")
		self.check(doc)


class TestBagLedger(FoundationTestCase):
	def test_bags_are_separate_rows_per_side(self):
		doc = entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GALI Raw - SSPP", bags=60)])
		entries = inv.bag_entries(doc)
		self.assertEqual([(e["warehouse"], e["bags"]) for e in entries], [("GODOWN Raw - SSPP", -60), ("GALI Raw - SSPP", 60)])
		self.assertEqual({e["entry_key"] for e in entries}, {"STE-00001|row1|OUT", "STE-00001|row1|IN"})
		self.assertEqual(entries[1]["season"], "Kharif 2025")
		self.assertEqual(entries[1]["physical_location"], "SSPP GALI")

	def test_row_without_bags_makes_no_entry(self):
		self.assertEqual(inv.bag_entries(entry("Material Receipt", [row(tgt="GODOWN Raw - SSPP", bags=0)])), [])

	def test_unmapped_warehouse_makes_no_entry(self):
		self.assertEqual(inv.bag_entries(entry("Material Receipt", [row(tgt="Stores - X", bags=5)])), [])

	def test_recording_twice_adds_nothing_the_second_time(self):
		doc = entry("Material Receipt", [row(tgt="GODOWN Raw - SSPP", bags=100)])
		new_doc = MagicMock()
		with patch.object(frappe, "get_doc", MagicMock(return_value=new_doc), create=True):
			self.db.exists.return_value = False
			inv.record_bag_ledger(doc)
			self.assertEqual(new_doc.insert.call_count, 1)
			self.db.exists.return_value = True  # key already there: a repeated call
			inv.record_bag_ledger(doc)
			self.assertEqual(new_doc.insert.call_count, 1)

	def test_leaving_more_bags_than_held_is_refused(self):
		doc = entry("Material Transfer", [row(src="GODOWN Raw - SSPP", tgt="GALI Raw - SSPP", bags=60)])
		with patch(f"{MODULE}.bag_balance", return_value=50):
			with self.assertRaises(frappe.ValidationError):
				inv.check_bag_balance_before_submit(doc)
		with patch(f"{MODULE}.bag_balance", return_value=60):
			inv.check_bag_balance_before_submit(doc)

	def test_two_rows_of_the_same_batch_are_added_together(self):
		doc = entry("Material Issue", [row(1, src="GODOWN Raw - SSPP", bags=40), row(2, src="GODOWN Raw - SSPP", bags=40)])
		with patch(f"{MODULE}.bag_balance", return_value=70):
			with self.assertRaises(frappe.ValidationError):
				inv.check_bag_balance_before_submit(doc)

	def test_cancel_reverses_once_and_keeps_the_original(self):
		original = frappe._dict(
			name="BLE-00001", entry_key="STE-00001|row1|IN", bags=100, posting_date="2026-10-27", company=SSPP,
			operating_unit="M050414", physical_location="SSPP GODOWN", warehouse="GODOWN Raw - SSPP", item_code="Paddy",
			batch_no="B-K25", season="Kharif 2025", voucher_type="Stock Entry", voucher_no="STE-00001", voucher_detail_no="row1",
		)
		new_doc = MagicMock()
		with patch.object(frappe, "get_all", MagicMock(return_value=[original]), create=True), patch.object(
			frappe, "get_doc", MagicMock(return_value=new_doc), create=True
		) as get_doc:
			self.db.exists.return_value = False
			with patch(f"{MODULE}.bag_balance", return_value=100):
				inv.reverse_bag_ledger(entry("Material Receipt", []))
			payload = get_doc.call_args[0][0]
			self.assertEqual(payload["bags"], -100)
			self.assertEqual(payload["entry_key"], "STE-00001|row1|IN|REV")
			self.assertEqual(payload["reverses"], "BLE-00001")
			self.assertEqual(payload["is_reversal"], 1)
			self.db.exists.return_value = True  # already reversed
			get_doc.reset_mock()
			inv.reverse_bag_ledger(entry("Material Receipt", []))
			get_doc.assert_not_called()


class TestSettingsItemRoles(FoundationTestCase):
	def settings(self, paddy="Paddy", raw="Raw Rice", boiled="Boiled Rice", by=("Bran", "Husk")):
		doc = StockPostingSettings.__new__(StockPostingSettings)
		doc.government_paddy_item, doc.raw_rice_item, doc.boiled_rice_item = paddy, raw, boiled
		doc.by_product_items = [frappe._dict(item_code=i) for i in by]
		return doc

	def setUp(self):
		super().setUp()
		self.db.get_value.return_value = frappe._dict(disabled=0, is_stock_item=1, has_batch_no=1, stock_uom="Quintal")

	def test_distinct_items_pass(self):
		self.settings().validate()

	def test_empty_settings_pass_because_nothing_is_chosen(self):
		self.settings(paddy="", raw="", boiled="", by=()).validate()

	def test_raw_and_boiled_rice_cannot_be_one_item(self):
		with self.assertRaises(frappe.ValidationError):
			self.settings(boiled="Raw Rice").validate()

	def test_paddy_cannot_be_a_rice_item(self):
		with self.assertRaises(frappe.ValidationError):
			self.settings(raw="Paddy").validate()

	def test_by_product_cannot_repeat_or_be_a_main_item(self):
		with self.assertRaises(frappe.ValidationError):
			self.settings(by=("Bran", "Bran")).validate()
		with self.assertRaises(frappe.ValidationError):
			self.settings(by=("Paddy",)).validate()

	def test_by_product_must_be_its_own_batch_tracked_stock_item(self):
		self.db.get_value.return_value = frappe._dict(disabled=0, is_stock_item=0, has_batch_no=1, stock_uom="Quintal")
		with self.assertRaises(frappe.ValidationError):
			self.settings().validate()
		self.db.get_value.return_value = frappe._dict(disabled=0, is_stock_item=1, has_batch_no=0, stock_uom="Quintal")
		with self.assertRaises(frappe.ValidationError):
			self.settings().validate()


class TestDuplicatePrevention(FoundationTestCase):
	def test_posting_reads_the_active_log_with_a_row_lock(self):
		self.db.get_value.return_value = frappe._dict(stock_entry="STE-1")
		sp.get_active_posting("GRN-1", for_update=True)
		self.assertTrue(self.db.get_value.call_args.kwargs.get("for_update"))
		sp.get_active_posting("GRN-1")
		self.assertFalse(self.db.get_value.call_args.kwargs.get("for_update"))

	def test_active_key_is_unique_in_the_log_and_bag_ledger_definitions(self):
		import json, os
		base = os.path.join(os.path.dirname(report.__file__), "..", "..", "doctype")
		for doctype, field in (("stock_posting_log", "active_key"), ("bag_ledger_entry", "entry_key")):
			path = os.path.join(base, doctype, f"{doctype}.json")
			with open(path) as handle:
				fields = {f["fieldname"]: f for f in json.load(handle)["fields"]}
			self.assertEqual(fields[field].get("unique"), 1, doctype)


class TestReport(FoundationTestCase):
	def data(self, **filters):
		warehouses = [RAW_GODOWN, BOILED_GODOWN, RAW_GALI, RGFP_RAW]
		balances = [
			{"warehouse": "GODOWN Raw - SSPP", "item_code": "Paddy", "batch_no": "B-K25", "qty": 100.0},
			{"warehouse": "GODOWN Boiled - SSPP", "item_code": "Paddy", "batch_no": "B-K25-2", "qty": 60.0},
			{"warehouse": "GALI Raw - SSPP", "item_code": "Paddy", "batch_no": "B-K25", "qty": 40.0},
			{"warehouse": "MAIN Raw - RGFP", "item_code": "Paddy", "batch_no": "B-K25", "qty": 25.0},
		]
		items = {"Paddy": {"stock_uom": "Quintal"}}
		bags = {("GODOWN Raw - SSPP", "Paddy", "B-K25"): 200, ("GODOWN Boiled - SSPP", "Paddy", "B-K25-2"): 120}
		types = {"M050414": "RAW", "M051007": "BOILED", "M050415": "RAW"}
		return report.build_rows(warehouses, balances, items, SEASONS, bags, types, frappe._dict(filters))

	def test_owners_share_one_location_and_combined_adds_them_once(self):
		rows = self.data()
		godown = [r for r in rows if r["physical_location"] == "SSPP GODOWN"]
		owners = [r for r in godown if not r.get("is_combined")]
		combined = [r for r in godown if r.get("is_combined")]
		self.assertEqual({r["operating_unit"] for r in owners}, {"M050414", "M051007"})
		self.assertEqual(len(combined), 1)
		self.assertEqual(combined[0]["qty"], 160.0)
		self.assertEqual(combined[0]["bags"], 320)
		self.assertEqual(combined[0]["operating_unit"], report.COMBINED)

	def test_two_gali_sites_are_never_added_together(self):
		rows = self.data()
		self.assertEqual({r["physical_location"] for r in rows}, {"SSPP GODOWN", "SSPP GALI", "RGFP MAIN GODOWN"})
		self.assertEqual(sum(r["qty"] for r in rows if r.get("is_combined")), 225.0)

	def test_combined_total_equals_sum_of_owner_rows(self):
		rows = self.data()
		owners = sum(r["qty"] for r in rows if not r.get("is_combined"))
		combined = sum(r["qty"] for r in rows if r.get("is_combined"))
		self.assertEqual(owners, combined)

	def test_bags_are_separate_from_quantity(self):
		rows = self.data()
		raw = next(r for r in rows if r["warehouse"] == "GODOWN Raw - SSPP")
		self.assertEqual((raw["qty"], raw["bags"], raw["uom"]), (100.0, 200, "Quintal"))
		self.assertEqual(raw["unit_type"], "RAW")

	def test_views_and_season_filter(self):
		self.assertTrue(all(not r.get("is_combined") for r in self.data(view=report.VIEW_OWNER_ONLY)))
		self.assertTrue(all(r.get("is_combined") for r in self.data(view=report.VIEW_COMBINED_ONLY)))
		self.assertEqual(self.data(season="Rabi 2026"), [])


class TestFoundationStatus(FoundationTestCase):
	def test_missing_companies_and_locations_are_reported_not_invented(self):
		with patch.object(frappe, "has_permission", MagicMock(return_value=True), create=True):
			def get_value(doctype, name=None, fieldname=None, *a, **k):
				if doctype == "Mill Master":
					return frappe._dict(name=name, type=inv.APPROVED_UNITS[name]["type"], company="x", accounting_company=None)
				return None
			self.db.get_value.side_effect = get_value
			self.db.exists.return_value = False
			status = inv.get_foundation_status()
		self.assertEqual(len(status["units"]), 5)
		self.assertTrue(all(not u["mapped"] for u in status["units"]))
		self.assertTrue(all(not u["expected_company_exists"] for u in status["units"]))
		self.assertEqual(len(status["locations"]), 9)
		self.assertTrue(any("does not exist yet" in issue for issue in status["issues"]))
		self.assertFalse(self.db.set_value.called)  # reads only


class TestReviewFixes(FoundationTestCase):
	def test_cancelling_a_receipt_is_blocked_when_its_bags_were_already_used(self):
		original = frappe._dict(
			name="BLE-00001", entry_key="STE-00001|row1|IN", bags=100, posting_date="2026-10-27", company=SSPP,
			operating_unit="M050414", physical_location="SSPP GODOWN", warehouse="GODOWN Raw - SSPP", item_code="Paddy",
			batch_no="B-K25", season="Kharif 2025", voucher_type="Stock Entry", voucher_no="STE-00001", voucher_detail_no="row1",
		)
		with patch.object(frappe, "get_all", MagicMock(return_value=[original]), create=True), patch.object(
			frappe, "get_doc", MagicMock(), create=True
		) as get_doc:
			self.db.exists.return_value = False
			with patch(f"{MODULE}.bag_balance", return_value=60):  # 40 bags already moved out
				with self.assertRaises(frappe.ValidationError):
					inv.reverse_bag_ledger(entry("Material Receipt", []))
			get_doc.assert_not_called()  # nothing half-written

	def test_transfer_for_manufacture_cannot_change_the_owner(self):
		same = entry("Material Transfer for Manufacture", [row(src="GODOWN Raw - SSPP", tgt="GALI Raw - SSPP")])
		self.check(same)  # same owner, new place: fine, no Transfer Kind needed
		self.refuses(entry("Material Transfer for Manufacture", [row(src="GODOWN Raw - SSPP", tgt="GODOWN Boiled - SSPP")]))
		self.refuses(entry("Send to Subcontractor", [row(src="GODOWN Raw - SSPP", tgt="Stores - X")]))

	def test_a_retired_warehouse_does_not_block_its_replacement(self):
		def get_value(doctype, filters=None, fieldname=None, *a, **k):
			if doctype == "Mill Master":
				return SSPP
			if doctype == "Physical Location":
				return frappe._dict(company=SSPP, is_active=1, shared_with_other_companies=0)
			if doctype == "Warehouse":
				self.assertEqual(filters.get("disabled"), 0)  # only live warehouses count
				return None
			return None

		self.db.get_value.side_effect = get_value
		self.db.exists.return_value = True
		sp.validate_warehouse(frappe._dict(
			name="GODOWN Raw v2 - SSPP", company=SSPP, operating_unit="M050414", physical_location="SSPP GODOWN", is_group=0, disabled=0
		))

	def test_report_reads_batches_the_erpnext_way(self):
		captured = {}
		self.db.sql.side_effect = lambda query, values=None, **k: captured.update(q=" ".join(query.split())) or []
		report._batch_balances(["W1"], {})
		q = captured["q"]
		self.assertIn("from `tabStock Ledger Entry` sle", q)
		self.assertIn("sbe.parent = sle.serial_and_batch_bundle", q)
		self.assertIn("sle.is_cancelled = 0", q)
		self.assertIn("sum(sbe.qty)", q)  # signed: outward rows are stored negative by ERPNext

	def test_guards_only_read_when_nothing_is_posted(self):
		"""The WBM -> Gate Exit -> GRN hooks do nothing, and write nothing, until a posting exists."""
		self.db.get_value.return_value = None
		with patch(f"{MODULE}.warehouse_ownership", return_value=None):
			sp.guard_grn_note(frappe._dict(name="GRN-1", net_weight=10))
			sp.guard_grn_note_trash(frappe._dict(name="GRN-1"))
			sp.guard_weigh_bridge(frappe._dict(name="WBM-1", net_weight=10))
			sp.guard_weigh_bridge_trash(frappe._dict(name="WBM-1"))
			sp.validate_stock_entry(frappe._dict(get=lambda k, d=None: d, flags=frappe._dict()))
			inv.validate_stock_entry_foundation(entry("Material Receipt", [row(tgt="Stores - X")]))
			inv.record_bag_ledger(entry("Material Receipt", [row(tgt="Stores - X", bags=5)]))
		for call in ("set_value", "sql", "commit"):
			self.assertFalse(getattr(self.db, call).called, call)


class TestNoDoubleCounting(FoundationTestCase):
	"""Randomised proof of the report's invariants: every quantity is counted once in the owner rows and once
	in the combined row of its location, and the two totals are equal."""

	def test_invariants_hold_for_random_stock(self):
		import random

		rng = random.Random(20261027)
		units = [("M050414", "RAW", SSPP), ("M051007", "BOILED", SSPP), ("M050415", "RAW", RGFP), ("M050410", "BOILED", RGFP)]
		locations = {SSPP: ["SSPP GODOWN", "SSPP GALI", "SSPP OPEN GODOWN"], RGFP: ["RGFP MAIN GODOWN", "RGFP GALI", "RGFP CHALAN"]}
		for _round in range(300):
			warehouses, seen = [], set()
			for code, kind, company in units:
				for place in rng.sample(locations[company], rng.randint(1, 3)):
					if (code, place) in seen:
						continue
					seen.add((code, place))
					warehouses.append(frappe._dict(name=f"{place}|{code}", company=company, operating_unit=code, physical_location=place))
			seasons = {f"B{n}": rng.choice(["Kharif 2025", "Rabi 2026"]) for n in range(4)}
			balances = [
				{"warehouse": w.name, "item_code": rng.choice(["Paddy", "Raw Rice"]), "batch_no": rng.choice(list(seasons)), "qty": round(rng.uniform(0.5, 500), 3)}
				for w in warehouses for _ in range(rng.randint(0, 3))
			]
			# a warehouse holds one (item, batch) once: merge repeats the way a SQL GROUP BY would
			merged = {}
			for b in balances:
				key = (b["warehouse"], b["item_code"], b["batch_no"])
				merged[key] = merged.get(key, 0) + b["qty"]
			balances = [{"warehouse": k[0], "item_code": k[1], "batch_no": k[2], "qty": round(v, 3)} for k, v in merged.items()]
			rows = report.build_rows(warehouses, balances, {"Paddy": {"stock_uom": "Quintal"}, "Raw Rice": {"stock_uom": "Quintal"}}, seasons, {}, {}, frappe._dict())
			owner = [r for r in rows if not r.get("is_combined")]
			combined = [r for r in rows if r.get("is_combined")]
			total_in = round(sum(b["qty"] for b in balances), 3)
			self.assertEqual(round(sum(r["qty"] for r in owner), 3), total_in)
			self.assertEqual(round(sum(r["qty"] for r in combined), 3), total_in)
			# one owner row per input row, one combined row per (location, item, season)
			self.assertEqual(len(owner), len(balances))
			self.assertEqual(len(combined), len({(r["physical_location"], r["item_code"], r["season"]) for r in owner}))
			# a combined row equals the sum of exactly its own owner rows
			for c in combined:
				mine = [o for o in owner if (o["physical_location"], o["item_code"], o["season"]) == (c["physical_location"], c["item_code"], c["season"])]
				self.assertEqual(round(sum(o["qty"] for o in mine), 3), c["qty"])
			# a warehouse sits in exactly one location, so no quantity can fall in two combined rows
			self.assertEqual(len({(o["warehouse"], o["physical_location"]) for o in owner}), len({o["warehouse"] for o in owner}))


class FakeBagLedger:
	"""In-memory stand-in for the Bag Ledger Entry table. The bag functions under test are the real ones."""

	def __init__(self):
		self.rows = []

	def get_doc(self, payload):
		ledger = self

		class Doc:
			def insert(self, **kwargs):
				entry = dict(payload)
				entry["name"] = f"BLE-{len(ledger.rows) + 1:05d}"
				entry.setdefault("is_reversal", 0)
				ledger.rows.append(frappe._dict(entry))

		return Doc()

	def exists(self, doctype, filters=None):
		return any(r.entry_key == filters["entry_key"] for r in self.rows)

	def get_all(self, doctype, filters=None, fields=None, **kwargs):
		return [r for r in self.rows if r.voucher_no == filters["voucher_no"] and not r.is_reversal]

	def balance(self, warehouse, item, batch, lock=False):
		return sum(r.bags for r in self.rows if (r.warehouse, r.item_code, r.batch_no or "") == (warehouse, item, batch or ""))

	def held(self, warehouse, batch="B-K25", item="Paddy"):
		return self.balance(warehouse, item, batch)

	def location_total(self, location):
		return sum(r.bags for r in self.rows if r.physical_location == location)


class TestCumulativeBagLedger(FoundationTestCase):
	"""Physical bags accumulate per warehouse (owner + location), item and batch. Every movement is a pair of rows."""

	def setUp(self):
		super().setUp()
		self.ledger = FakeBagLedger()
		for patcher in (
			patch.object(frappe, "get_doc", self.ledger.get_doc, create=True),
			patch.object(frappe, "get_all", self.ledger.get_all, create=True),
			patch(f"{MODULE}.bag_balance", side_effect=self.ledger.balance),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.db.exists.side_effect = lambda doctype, filters=None: self.ledger.exists(doctype, filters)

	def submit(self, doc):
		inv.validate_stock_entry_foundation(doc)
		inv.check_bag_balance_before_submit(doc)
		inv.record_bag_ledger(doc)

	def cancel(self, doc):
		inv.reverse_bag_ledger(doc)

	def receipt(self, name, bags, warehouse="GODOWN Raw - SSPP", batch="B-K25"):
		return entry("Material Receipt", [row(tgt=warehouse, batch=batch, bags=bags)], name=name)

	def transfer(self, name, bags, src, tgt, kind=inv.PHYSICAL, reason="", batch="B-K25"):
		return entry("Material Transfer", [row(src=src, tgt=tgt, batch=batch, bags=bags)], name=name, transfer_kind=kind, ownership_transfer_reason=reason)

	def test_balances_accumulate_across_distinct_receipts(self):
		self.submit(self.receipt("STE-A", 196))
		self.submit(self.receipt("STE-B", 177))  # a different physical load, same warehouse and batch
		self.submit(self.receipt("STE-C", 100, batch="B-K25-2"))  # another batch stays separate
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 373)
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP", batch="B-K25-2"), 100)

	def test_same_owner_physical_transfer_moves_bags_between_locations(self):
		self.submit(self.receipt("STE-A", 373))
		self.submit(self.transfer("STE-T", 100, "GODOWN Raw - SSPP", "GALI Raw - SSPP"))
		self.assertEqual((self.ledger.held("GODOWN Raw - SSPP"), self.ledger.held("GALI Raw - SSPP")), (273, 100))
		self.assertEqual(self.ledger.location_total("SSPP GODOWN") + self.ledger.location_total("SSPP GALI"), 373)  # nothing created or lost

	def test_ownership_transfer_changes_owner_but_not_the_location_total(self):
		self.submit(self.receipt("STE-A", 273))
		before = self.ledger.location_total("SSPP GODOWN")
		self.submit(self.transfer("STE-O", 50, "GODOWN Raw - SSPP", "GODOWN Boiled - SSPP", inv.OWNERSHIP, "Raw paddy sent for parboiling"))
		self.assertEqual((self.ledger.held("GODOWN Raw - SSPP"), self.ledger.held("GODOWN Boiled - SSPP")), (223, 50))
		self.assertEqual(self.ledger.location_total("SSPP GODOWN"), before)  # same physical place, two owners, counted once
		rows = [r for r in self.ledger.rows if r.voucher_no == "STE-O"]
		self.assertEqual({(r.operating_unit, r.bags) for r in rows}, {("M050414", -50), ("M051007", 50)})

	def test_insufficient_bags_are_rejected_and_nothing_is_written(self):
		self.submit(self.receipt("STE-A", 196))
		self.submit(self.transfer("STE-T", 100, "GODOWN Raw - SSPP", "GALI Raw - SSPP"))
		written = len(self.ledger.rows)
		with self.assertRaises(frappe.ValidationError):
			self.submit(self.transfer("STE-X", 500, "GALI Raw - SSPP", "GODOWN Raw - SSPP"))  # GALI holds only 100
		self.assertEqual(len(self.ledger.rows), written)
		self.assertEqual(self.ledger.held("GALI Raw - SSPP"), 100)

	def test_stock_leaving_a_bagged_warehouse_must_state_the_bags(self):
		self.submit(self.receipt("STE-A", 196))
		with self.assertRaises(frappe.ValidationError):
			self.submit(self.transfer("STE-T", 0, "GODOWN Raw - SSPP", "GALI Raw - SSPP"))
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 196)

	def test_cancelling_a_receipt_is_blocked_while_its_bags_are_elsewhere_then_works_after_they_return(self):
		receipt = self.receipt("STE-A", 196)
		self.submit(receipt)
		transfer = self.transfer("STE-T", 150, "GODOWN Raw - SSPP", "GALI Raw - SSPP")
		self.submit(transfer)  # 46 bags left in the godown
		with self.assertRaises(frappe.ValidationError):
			self.cancel(receipt)  # needs 196 back, only 46 are there
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 46)
		self.cancel(transfer)  # reverse the transfer first: godown 196, gali 0
		self.assertEqual((self.ledger.held("GODOWN Raw - SSPP"), self.ledger.held("GALI Raw - SSPP")), (196, 0))
		self.cancel(receipt)
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 0)
		self.assertTrue(all(r.bags != 0 for r in self.ledger.rows))
		self.assertEqual(sum(r.bags for r in self.ledger.rows), 0)  # originals stay, reversals net them to zero

	def test_cancelling_an_ownership_transfer_restores_both_owners(self):
		self.submit(self.receipt("STE-A", 100))
		owner = self.transfer("STE-O", 40, "GODOWN Raw - SSPP", "GODOWN Boiled - SSPP", inv.OWNERSHIP, "parboil")
		self.submit(owner)
		self.cancel(owner)
		self.assertEqual((self.ledger.held("GODOWN Raw - SSPP"), self.ledger.held("GODOWN Boiled - SSPP")), (100, 0))

	def test_the_same_movement_is_never_counted_twice(self):
		receipt = self.receipt("STE-A", 196)
		self.submit(receipt)
		inv.record_bag_ledger(receipt)  # a repeated call (retry, double hook)
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 196)
		self.cancel(receipt)
		self.cancel(receipt)  # a repeated cancel adds no second reversal
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 0)
		self.assertEqual(len(self.ledger.rows), 2)


class TestGovernmentOnlyBagLedger(TestCumulativeBagLedger):
	"""Bags are tracked for government paddy only. Local paddy, rice and by-products never enter or move this ledger."""

	def local_receipt(self, name, bags, warehouse="GODOWN Raw - SSPP"):
		return entry("Material Receipt", [row(tgt=warehouse, batch="B-LOCAL", bags=bags)], name=name)

	def test_government_paddy_records_the_physical_bags(self):
		self.submit(self.receipt("STE-G", 196))
		rows = [r for r in self.ledger.rows if r.voucher_no == "STE-G"]
		self.assertEqual([(r.bags, r.batch_no, r.item_code) for r in rows], [(196, "B-K25", "Paddy")])

	def test_local_paddy_creates_no_government_bag_entry(self):
		self.submit(self.local_receipt("STE-L", 300))
		self.assertEqual(self.ledger.rows, [])
		self.assertEqual(inv.bag_entries(self.local_receipt("STE-L", 300)), [])

	def test_local_movements_do_not_touch_the_government_balance(self):
		self.submit(self.receipt("STE-G", 196))
		self.submit(self.local_receipt("STE-L", 300))
		local_transfer = self.transfer("STE-LT", 300, "GODOWN Raw - SSPP", "GALI Raw - SSPP", batch="B-LOCAL")
		self.submit(local_transfer)  # 300 local bags leave although the ledger holds only 196: they are not in it
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 196)
		self.assertEqual(self.ledger.held("GALI Raw - SSPP"), 0)
		self.assertEqual(len(self.ledger.rows), 1)  # only the government receipt's single in-row; the local rows never exist
		self.cancel(local_transfer)  # nothing to reverse, and nothing is added
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 196)

	def test_local_stock_may_leave_a_bagged_warehouse_without_stating_bags(self):
		self.submit(self.receipt("STE-G", 196))
		self.submit(self.transfer("STE-LT", 0, "GODOWN Raw - SSPP", "GALI Raw - SSPP", batch="B-LOCAL"))  # no bags rule for local
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 196)

	def test_rice_and_by_products_are_not_in_the_government_bag_ledger(self):
		self.submit(entry("Material Receipt", [row(item="Raw Rice", tgt="GODOWN Raw - SSPP", bags=100), row(2, item="Bran", tgt="GODOWN Raw - SSPP", bags=20)], name="STE-R"))
		self.assertEqual(self.ledger.rows, [])

	def test_a_batch_with_no_recorded_procurement_type_is_never_assumed_government(self):
		self.submit(entry("Material Receipt", [row(tgt="GODOWN Raw - SSPP", batch="B-UNTYPED", bags=50)], name="STE-U"))
		self.assertEqual(self.ledger.rows, [])

	def test_government_and_local_batches_in_one_row_are_refused_so_bags_cannot_be_misattributed(self):
		mixed = row(src="GODOWN Raw - SSPP", batch="", bags=40)
		mixed.serial_and_batch_bundle = "SBB-1"
		with patch.object(frappe, "get_all", MagicMock(return_value=["B-K25", "B-LOCAL"]), create=True):
			with self.assertRaises(frappe.ValidationError):
				inv.bag_entries(entry("Manufacture", [mixed], name="STE-M"))

	def test_no_government_paddy_item_configured_means_nothing_is_tracked(self):
		with patch.object(frappe, "get_cached_doc", MagicMock(return_value=frappe._dict(government_paddy_item="", raw_rice_item="", boiled_rice_item="")), create=True):
			self.assertEqual(inv.bag_entries(self.receipt("STE-G", 196)), [])

	def test_government_balance_is_still_protected_while_local_is_ignored(self):
		self.submit(self.receipt("STE-G", 196))
		self.submit(self.local_receipt("STE-L", 900))
		with self.assertRaises(frappe.ValidationError):
			self.submit(self.transfer("STE-X", 300, "GODOWN Raw - SSPP", "GALI Raw - SSPP"))  # government batch holds only 196
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 196)

	def test_government_cumulative_balance_across_receipts_transfers_and_cancellation_with_local_noise(self):
		a, b = self.receipt("STE-A", 196), self.receipt("STE-B", 177)
		self.submit(a); self.submit(b); self.submit(self.local_receipt("STE-L", 500))
		t = self.transfer("STE-T", 100, "GODOWN Raw - SSPP", "GALI Raw - SSPP"); self.submit(t)
		o = self.transfer("STE-O", 50, "GODOWN Raw - SSPP", "GODOWN Boiled - SSPP", inv.OWNERSHIP, "parboil"); self.submit(o)
		self.assertEqual((self.ledger.held("GODOWN Raw - SSPP"), self.ledger.held("GALI Raw - SSPP"), self.ledger.held("GODOWN Boiled - SSPP")), (223, 100, 50))
		self.assertEqual(sum(r.bags for r in self.ledger.rows), 373)  # the two government loads, once each; the 500 local bags are absent
		self.cancel(o); self.cancel(t)
		self.assertEqual(self.ledger.held("GODOWN Raw - SSPP"), 373)


if __name__ == "__main__":
	unittest.main()
