# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Inventory configuration plan. Mocked tests: no site, no database."""

import copy
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement import inventory_setup as setup
from ivri_od.procurement.inventory_foundation import APPROVED_UNITS, LEGAL_COMPANIES, approved_location_names

MODULE = "ivri_od.procurement.inventory_setup"
TEMPLATE = dict(
	default_currency="INR", country="India", valuation_method="FIFO", chart_of_accounts="Standard",
	create_chart_of_accounts_based_on="Standard Template", enable_perpetual_inventory=1,
)
OLD_COMPANIES = {
	"Shree Shyamji Paddy Processing Pvt Ltd (Boiled)": "SSPPB",
	"Shree Shyamji Paddy Processing Pvt Ltd (Raw)": "SSPPR",
	"Radhe Govind Food Products (Boiled)": "RGFB",
	"Radhe Govind Food Products (Raw)": "RGFR",
	"Laddu Gopal Industries (Boiled)": "LGIB",
}
MILLS = {
	"M050414": "RAW", "M051007": "BOILED", "M050415": "RAW", "M050410": "BOILED", "M050421": "BOILED",
}
NO_APPROVALS = {"warehouses": [], "items": []}


def snapshot(**overrides):
	snap = {
		"companies": {n: frappe._dict(name=n, abbr=a, **TEMPLATE) for n, a in OLD_COMPANIES.items()},
		"locations": {},
		"mills": {c: frappe._dict(name=c, type=t, accounting_company=None) for c, t in MILLS.items()},
		"warehouses": [],
		"items": {},
		"item_groups": {"Raw Material", "Products"},
		"uoms": {"Quintal", "Kg"},
		"settings": {"enabled": 0, "government_paddy_item": "", "raw_rice_item": "", "boiled_rice_item": "", "by_products": []},
	}
	snap.update(overrides)
	return snap


def actions(plan, kind=None):
	return {s["id"]: s["action"] for s in plan["steps"] if kind is None or s["kind"] == kind}


def fully_configured():
	snap = snapshot()
	for name, abbr in LEGAL_COMPANIES.items():
		snap["companies"][abbr] = None
	snap["companies"] = {n: frappe._dict(name=n, abbr=a, **TEMPLATE) for n, a in OLD_COMPANIES.items()}
	for abbr, name in LEGAL_COMPANIES.items():
		snap["companies"][name] = frappe._dict(name=name, abbr=abbr, **TEMPLATE)
	snap["locations"] = {loc: LEGAL_COMPANIES[loc.split(" ")[0]] for loc in approved_location_names()}
	for code in snap["mills"]:
		snap["mills"][code].accounting_company = LEGAL_COMPANIES[APPROVED_UNITS[code]["abbr"]]
	return snap


class TestPlanFromCurrentState(unittest.TestCase):
	"""The state of shyamji today: five suffixed Companies, nothing else configured."""

	def setUp(self):
		self.plan = setup.plan_from_snapshot(snapshot(), NO_APPROVALS)

	def test_three_legal_companies_are_planned_not_the_old_five(self):
		companies = actions(self.plan, "Company")
		self.assertEqual(companies, {"company:SSPP": "create", "company:RGFP": "create", "company:LGI": "create"})
		create = next(s for s in self.plan["steps"] if s["id"] == "company:SSPP")
		self.assertEqual(create["values"]["company_name"], "Shree Shyamji Paddy Processing Pvt Ltd")
		self.assertEqual(create["values"]["abbr"], "SSPP")

	def test_company_settings_are_copied_from_the_existing_ones_not_invented(self):
		create = next(s for s in self.plan["steps"] if s["id"] == "company:LGI")
		for field, value in TEMPLATE.items():
			self.assertEqual(create["values"][field], value)

	def test_nine_locations_planned_after_their_company(self):
		locations = [s for s in self.plan["steps"] if s["kind"] == "Physical Location"]
		self.assertEqual(len(locations), 9)
		self.assertTrue(all(s["action"] == "create" for s in locations))
		gali = {s["name"]: s for s in locations if s["name"].endswith(" GALI")}
		self.assertEqual(set(gali), {"SSPP GALI", "RGFP GALI"})
		self.assertNotEqual(gali["SSPP GALI"]["values"]["company"], gali["RGFP GALI"]["values"]["company"])
		self.assertEqual(gali["SSPP GALI"]["depends_on"], ["company:SSPP"])

	def test_five_units_get_only_their_approved_company(self):
		units = {s["name"]: s for s in self.plan["steps"] if s["kind"] == "Mill Master"}
		self.assertEqual(len(units), 5)
		for code, step in units.items():
			self.assertEqual(step["action"], "update")
			self.assertEqual(step["values"], {"accounting_company": LEGAL_COMPANIES[APPROVED_UNITS[code]["abbr"]]})
		self.assertEqual(units["M050410"]["values"]["accounting_company"], "Radhe Govind Food Products")

	def test_warehouses_and_items_are_pending_not_guessed(self):
		self.assertEqual(actions(self.plan, "Warehouse"), {"warehouses:pending": "pending_decision"})
		self.assertEqual(actions(self.plan, "Item"), {"items:pending": "pending_decision"})
		self.assertEqual(len(self.plan["pending"]), 2)
		candidates = self.plan["pending"][0]["values"]["candidates"]
		self.assertEqual(len(candidates), 15)  # shown for the decision only, nothing is created from them

	def test_nothing_is_blocked_and_existing_companies_are_not_planned_for_change(self):
		self.assertEqual(self.plan["blocked"], [])
		self.assertFalse([s for s in self.plan["steps"] if s["name"] in OLD_COMPANIES])

	def test_plan_hash_is_stable_and_changes_with_the_state(self):
		again = setup.plan_from_snapshot(snapshot(), NO_APPROVALS)
		self.assertEqual(again["plan_hash"], self.plan["plan_hash"])
		other = setup.plan_from_snapshot(fully_configured(), NO_APPROVALS)
		self.assertNotEqual(other["plan_hash"], self.plan["plan_hash"])


class TestIdempotence(unittest.TestCase):
	def test_when_everything_exists_nothing_is_actionable(self):
		plan = setup.plan_from_snapshot(fully_configured(), NO_APPROVALS)
		self.assertFalse([s for s in plan["steps"] if s["action"] in setup.ACTIONABLE])
		self.assertEqual(plan["counts"].get("exists"), 3 + 9 + 5)

	def test_partly_configured_plans_only_the_rest(self):
		snap = fully_configured()
		del snap["locations"]["LGI PLANT"]
		snap["mills"]["M050421"].accounting_company = None
		plan = setup.plan_from_snapshot(snap, NO_APPROVALS)
		self.assertEqual({s["id"] for s in plan["steps"] if s["action"] in setup.ACTIONABLE}, {"location:LGI PLANT", "unit:M050421"})


class TestBlocked(unittest.TestCase):
	def blocked(self, snap, approved=NO_APPROVALS):
		return {s["id"]: s["note"] for s in setup.plan_from_snapshot(snap, approved)["blocked"]}

	def test_abbreviation_already_used_by_another_company(self):
		snap = snapshot()
		snap["companies"]["Other Co"] = frappe._dict(name="Other Co", abbr="SSPP", **TEMPLATE)
		blocked = self.blocked(snap)
		self.assertIn("company:SSPP", blocked)
		self.assertIn("location:SSPP GODOWN", blocked)  # nothing is built on a Company that cannot be made

	def test_existing_company_with_other_abbreviation_is_never_changed(self):
		snap = fully_configured()
		snap["companies"][LEGAL_COMPANIES["LGI"]].abbr = "LG"
		self.assertIn("company:LGI", self.blocked(snap))

	def test_existing_companies_that_disagree_block_company_creation(self):
		snap = snapshot()
		snap["companies"]["Laddu Gopal Industries (Boiled)"].valuation_method = "Moving Average"
		self.assertIn("valuation_method", self.blocked(snap)["company:SSPP"])

	def test_unit_already_mapped_to_another_company_is_not_overwritten(self):
		snap = fully_configured()
		snap["mills"]["M051007"].accounting_company = "Radhe Govind Food Products"
		self.assertIn("unit:M051007", self.blocked(snap))

	def test_unit_with_wrong_type_or_missing_is_blocked(self):
		snap = fully_configured()
		snap["mills"]["M050414"].type = "BOILED"
		del snap["mills"]["M050421"]
		blocked = self.blocked(snap)
		self.assertIn("unit:M050414", blocked)
		self.assertIn("unit:M050421", blocked)

	def test_location_under_the_wrong_company_is_blocked(self):
		snap = fully_configured()
		snap["locations"]["RGFP GALI"] = LEGAL_COMPANIES["SSPP"]
		self.assertIn("location:RGFP GALI", self.blocked(snap))


class TestWarehousePairs(unittest.TestCase):
	def plan(self, pairs, snap=None):
		return setup.plan_from_snapshot(snap or fully_configured(), {"warehouses": pairs, "items": []})

	def test_approved_pair_becomes_one_named_warehouse(self):
		plan = self.plan([{"unit": "M050414", "location": "SSPP GODOWN"}, {"unit": "M051007", "location": "SSPP GODOWN"}])
		steps = {s["id"]: s for s in plan["steps"] if s["kind"] == "Warehouse"}
		raw, boiled = steps["warehouse:M050414|SSPP GODOWN"], steps["warehouse:M051007|SSPP GODOWN"]
		self.assertEqual((raw["name"], boiled["name"]), ("GODOWN Raw - SSPP", "GODOWN Boiled - SSPP"))  # two owners, one place
		self.assertEqual(raw["values"]["operating_unit"], "M050414")
		self.assertEqual(raw["values"]["physical_location"], "SSPP GODOWN")
		self.assertEqual(raw["values"]["parent_warehouse"], "All Warehouses - SSPP")
		self.assertNotIn("warehouses:pending", steps)

	def test_existing_pair_is_not_created_again(self):
		snap = fully_configured()
		snap["warehouses"] = [frappe._dict(name="GODOWN Raw - SSPP", company=LEGAL_COMPANIES["SSPP"], operating_unit="M050414", physical_location="SSPP GODOWN", disabled=0, is_group=0)]
		plan = self.plan([{"unit": "M050414", "location": "SSPP GODOWN"}], snap)
		self.assertEqual(actions(plan, "Warehouse"), {"warehouse:M050414|SSPP GODOWN": "exists"})

	def test_unapproved_or_cross_company_pairs_are_blocked(self):
		plan = self.plan([
			{"unit": "M050414", "location": "RGFP GALI"},      # another legal Company's site
			{"unit": "M999999", "location": "SSPP GALI"},       # unknown unit
			{"unit": "M050414", "location": "SSPP BACK YARD"},  # not one of the nine
			{"unit": "M050414", "location": "SSPP GALI"},
			{"unit": "M050414", "location": "SSPP GALI"},       # listed twice
		])
		blocked = {s["id"] for s in plan["blocked"]}
		self.assertEqual(len(blocked), 4)
		self.assertIn("warehouse:M050414|RGFP GALI", blocked)


class TestItems(unittest.TestCase):
	ITEMS = [
		{"role": "paddy", "item_code": "Paddy", "item_name": "Paddy", "item_group": "Raw Material"},
		{"role": "raw_rice", "item_code": "Raw Rice", "item_name": "Raw Rice", "item_group": "Products"},
		{"role": "boiled_rice", "item_code": "Boiled Rice", "item_name": "Boiled Rice", "item_group": "Products"},
		{"role": "by_product", "item_code": "Bran", "item_name": "Bran", "item_group": "Products"},
	]

	def plan(self, items, snap=None):
		return setup.plan_from_snapshot(snap or fully_configured(), {"warehouses": [], "items": items})

	def test_items_are_batch_tracked_stock_items_in_quintal(self):
		plan = self.plan(self.ITEMS)
		items = [s for s in plan["steps"] if s["kind"] == "Item"]
		self.assertEqual({s["name"] for s in items if s["action"] == "create"}, {"Paddy", "Raw Rice", "Boiled Rice", "Bran"})
		for s in items:
			if s["action"] == "create":
				self.assertEqual((s["values"]["stock_uom"], s["values"]["is_stock_item"], s["values"]["has_batch_no"]), ("Quintal", 1, 1))
				self.assertNotIn("valuation_rate", s["values"])  # no rate is ever set

	def test_raw_and_boiled_rice_are_separate_items_and_paddy_is_one(self):
		steps = [s for s in self.plan(self.ITEMS)["steps"] if s["kind"] == "Stock Posting Settings" and "by_product_item" not in s["values"]]
		fields = {field: value for s in steps for field, value in s["values"].items()}
		self.assertEqual(fields, {"government_paddy_item": "Paddy", "raw_rice_item": "Raw Rice", "boiled_rice_item": "Boiled Rice"})
		self.assertEqual(len(set(fields.values())), 3)
		by = [s["values"]["by_product_item"] for s in self.plan(self.ITEMS)["steps"] if "by_product_item" in s["values"]]
		self.assertEqual(by, ["Bran"])

	def test_missing_or_duplicate_core_role_is_blocked(self):
		self.assertTrue(self.plan([i for i in self.ITEMS if i["role"] != "boiled_rice"])["blocked"])
		self.assertTrue(self.plan(self.ITEMS + [dict(self.ITEMS[0], item_code="Paddy 2")])["blocked"])

	def test_unknown_group_blocks_and_existing_item_is_left_alone(self):
		bad = [dict(self.ITEMS[0], item_group="Nowhere")] + self.ITEMS[1:]
		self.assertTrue(self.plan(bad)["blocked"])
		snap = fully_configured()
		snap["items"] = {"Paddy": frappe._dict(name="Paddy", item_group="Raw Material")}
		steps = {s["name"]: s["action"] for s in self.plan(self.ITEMS, snap)["steps"] if s["kind"] == "Item"}
		self.assertEqual(steps["Paddy"], "exists")

	def test_settings_already_pointing_elsewhere_is_blocked_and_enabled_is_never_planned(self):
		snap = fully_configured()
		snap["settings"]["government_paddy_item"] = "Some Other Item"
		plan = self.plan(self.ITEMS, snap)
		self.assertTrue(any(s["id"] == "settings:paddy" for s in plan["blocked"]))
		self.assertFalse(any("enabled" in s["values"] for s in plan["steps"]))


class TestApply(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.plan = setup.plan_from_snapshot(snapshot(), NO_APPROVALS)
		self.created = []

		def get_doc(*args, **kwargs):
			spec = args[0]
			doc = MagicMock()
			doc.accounting_company = None
			doc.name = spec.get("warehouse_name") if isinstance(spec, dict) else spec
			doc.insert.side_effect = lambda: self.created.append(("insert", spec["doctype"], spec.get("company_name") or spec.get("location_name")))
			doc.save.side_effect = lambda: self.created.append(("save", args[0], doc.accounting_company, args[1] if len(args) > 1 else None))
			return doc

		def throw(msg, *a, **k):
			raise frappe.ValidationError(msg)

		for patcher in (
			patch.object(frappe, "only_for", MagicMock(), create=True),
			patch.object(frappe, "throw", throw, create=True),
			patch.object(frappe, "get_doc", get_doc, create=True),
			patch(f"{MODULE}.build_plan", side_effect=lambda: self.plan),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_wrong_hash_changes_nothing(self):
		with self.assertRaises(frappe.ValidationError):
			setup.apply_plan("not-the-reviewed-hash")
		self.assertEqual(self.created, [])

	def test_posting_enabled_blocks_apply(self):
		self.plan["posting_enabled"] = 1
		with self.assertRaises(frappe.ValidationError):
			setup.apply_plan(self.plan["plan_hash"])
		self.assertEqual(self.created, [])

	def test_blocked_plan_changes_nothing(self):
		self.plan["blocked"] = [{"id": "x", "note": "y"}]
		with self.assertRaises(frappe.ValidationError):
			setup.apply_plan(self.plan["plan_hash"])
		self.assertEqual(self.created, [])

	def test_reviewed_plan_runs_in_dependency_order_and_only_creates_or_fills_empty_fields(self):
		result = setup.apply_plan(self.plan["plan_hash"])
		self.assertEqual(len(result["applied"]), 3 + 9 + 5)
		self.assertEqual(result["skipped_missing_dependency"], [])
		kinds = [c[1] for c in self.created if c[0] == "insert"]
		self.assertEqual(kinds[:3], ["Company"] * 3)  # Companies first
		self.assertEqual(kinds[3:], ["Physical Location"] * 9)
		saved = [c for c in self.created if c[0] == "save"]
		self.assertEqual(len(saved), 5)  # five Mill Master records, only their empty field filled
		self.assertEqual({c[1] for c in saved}, {"Mill Master"})
		for _kind, _doctype, company, code in saved:  # each unit received exactly its approved legal Company
			self.assertEqual(company, LEGAL_COMPANIES[APPROVED_UNITS[code]["abbr"]])
		self.assertEqual({c[3] for c in saved}, set(APPROVED_UNITS))

	def test_a_step_whose_dependency_never_completed_is_skipped_not_run(self):
		for step in self.plan["steps"]:
			if step["id"] == "location:SSPP GALI":
				step["depends_on"] = ["company:DOES-NOT-EXIST"]
		self.plan["plan_hash"] = "reviewed"  # the hash is not what this test is about
		with patch(f"{MODULE}.build_plan", return_value=self.plan):
			result = setup.apply_plan("reviewed")
		self.assertEqual(result["skipped_missing_dependency"], ["location:SSPP GALI"])
		self.assertNotIn("location:SSPP GALI", result["applied"])
		self.assertNotIn(("insert", "Physical Location", "SSPP GALI"), self.created)

	def test_filling_an_already_mapped_mill_master_is_refused(self):
		step = {"id": "unit:M051007", "kind": "Mill Master", "name": "M051007", "action": "update", "values": {"accounting_company": "X"}, "depends_on": [], "note": ""}
		existing = MagicMock()
		existing.accounting_company = "Already Set"
		with patch.object(frappe, "get_doc", MagicMock(return_value=existing), create=True):
			with self.assertRaises(frappe.ValidationError):
				setup._run_step(step)
		existing.save.assert_not_called()


class TestSharedWarehouses(unittest.TestCase):
	"""One shared warehouse per physical location, under the legal Company. Raw and Boiled share it."""

	def plan(self, entries, snap=None):
		return setup.plan_from_snapshot(snap or fully_configured(), {"warehouses": entries, "items": []})

	def warehouse(self, name, company, location, unit=None, disabled=0):
		return frappe._dict(name=name, company=company, operating_unit=unit, physical_location=location, disabled=disabled, is_group=0)

	def test_a_location_becomes_one_shared_warehouse_without_an_operating_unit(self):
		plan = self.plan([{"location": "SSPP GODOWN"}])
		step = next(s for s in plan["steps"] if s["kind"] == "Warehouse")
		self.assertEqual((step["id"], step["name"], step["action"]), ("warehouse:shared|SSPP GODOWN", "GODOWN - SSPP", "create"))
		self.assertEqual(
			step["values"],
			{"warehouse_name": "GODOWN", "company": LEGAL_COMPANIES["SSPP"], "parent_warehouse": "All Warehouses - SSPP", "physical_location": "SSPP GODOWN"},
		)
		self.assertEqual(step["depends_on"], ["company:SSPP", "location:SSPP GODOWN"])

	def test_the_two_gali_stay_two_places_under_two_companies(self):
		plan = self.plan([{"location": "SSPP GALI"}, {"location": "RGFP GALI"}])
		names = {s["name"]: s["values"]["company"] for s in plan["steps"] if s["kind"] == "Warehouse"}
		self.assertEqual(names, {"GALI - SSPP": LEGAL_COMPANIES["SSPP"], "GALI - RGFP": LEGAL_COMPANIES["RGFP"]})

	def test_an_existing_shared_warehouse_is_not_created_again(self):
		snap = fully_configured()
		snap["warehouses"] = [self.warehouse("GODOWN - SSPP", LEGAL_COMPANIES["SSPP"], "SSPP GODOWN")]
		plan = self.plan([{"location": "SSPP GODOWN"}], snap)
		self.assertEqual(actions(plan, "Warehouse"), {"warehouse:shared|SSPP GODOWN": "exists"})

	def test_an_older_per_unit_warehouse_at_the_location_does_not_count_as_the_shared_one(self):
		snap = fully_configured()
		snap["warehouses"] = [self.warehouse("GODOWN Raw - SSPP", LEGAL_COMPANIES["SSPP"], "SSPP GODOWN", unit="M050414")]
		plan = self.plan([{"location": "SSPP GODOWN"}], snap)
		self.assertEqual(actions(plan, "Warehouse")["warehouse:shared|SSPP GODOWN"], "create")

	def test_a_disabled_shared_warehouse_is_not_counted_as_live(self):
		snap = fully_configured()
		snap["warehouses"] = [self.warehouse("GODOWN - SSPP", LEGAL_COMPANIES["SSPP"], "SSPP GODOWN", disabled=1)]
		self.assertEqual(actions(self.plan([{"location": "SSPP GODOWN"}], snap))["warehouse:shared|SSPP GODOWN"], "create")

	def test_a_location_listed_twice_or_unknown_is_blocked(self):
		plan = self.plan([{"location": "SSPP GALI"}, {"location": "SSPP GALI"}, {"location": "SSPP BACK YARD"}, {"location": "XYZ GODOWN"}])
		self.assertEqual(len(plan["blocked"]), 3)

	def test_running_the_plan_twice_converges_without_duplicates(self):
		approved = [{"location": loc} for loc in approved_location_names()]
		snap = fully_configured()
		first = self.plan(approved, snap)
		created = [s for s in first["steps"] if s["kind"] == "Warehouse" and s["action"] == "create"]
		self.assertEqual(len(created), 9)
		snap["warehouses"] = [
			self.warehouse(s["name"], s["values"]["company"], s["values"]["physical_location"]) for s in created
		]
		second = self.plan(approved, snap)
		self.assertEqual({s["action"] for s in second["steps"] if s["kind"] == "Warehouse"}, {"exists"})
		self.assertEqual(second["counts"].get("create", 0), 0)

	def test_the_fifteen_older_warehouses_are_listed_for_retirement_but_never_run_by_apply(self):
		snap = fully_configured()
		legacy = []
		for code, spec in APPROVED_UNITS.items():
			for short in __import__("ivri_od.procurement.inventory_foundation", fromlist=["x"]).APPROVED_LOCATIONS[spec["abbr"]]:
				legacy.append(self.warehouse(f"{short} {spec['type'].title()} - {spec['abbr']}", LEGAL_COMPANIES[spec["abbr"]], f"{spec['abbr']} {short}", unit=code))
		snap["warehouses"] = legacy
		plan = self.plan([{"location": loc} for loc in approved_location_names()], snap)
		retire = [s for s in plan["steps"] if s["action"] == setup.RETIRE]
		self.assertEqual((len(legacy), len(retire)), (15, 15))
		self.assertTrue(all(s["id"].startswith("legacy:") for s in retire))
		self.assertNotIn(setup.RETIRE, setup.ACTIONABLE)

	def test_nothing_is_listed_for_retirement_when_no_shared_warehouse_is_approved(self):
		snap = fully_configured()
		snap["warehouses"] = [self.warehouse("GODOWN Raw - SSPP", LEGAL_COMPANIES["SSPP"], "SSPP GODOWN", unit="M050414")]
		plan = self.plan([{"unit": "M050414", "location": "SSPP GODOWN"}], snap)
		self.assertEqual([s for s in plan["steps"] if s["action"] == setup.RETIRE], [])

	def test_older_per_unit_entries_are_still_understood(self):
		plan = self.plan([{"unit": "M050414", "location": "SSPP GODOWN"}, {"location": "SSPP GALI"}])
		self.assertEqual(
			actions(plan, "Warehouse"),
			{"warehouse:M050414|SSPP GODOWN": "create", "warehouse:shared|SSPP GALI": "create"},
		)


class TestDeleteLegacyWarehouses(unittest.TestCase):
	REPORT = [
		{"name": "A Raw - SSPP", "disabled": 0, "blocked_by": []},
		{"name": "A Boiled - SSPP", "disabled": 0, "blocked_by": []},
		{"name": "B Raw - SSPP", "disabled": 0, "blocked_by": ["1 stock ledger entries"]},
		{"name": "C Raw - SSPP", "disabled": 0, "blocked_by": ["its physical location has no shared warehouse yet"]},
		{"name": "D Raw - SSPP", "disabled": 1, "blocked_by": []},
	]

	def _run(self, report, confirmation=setup.DELETE_CONFIRMATION, posting=0, delete_side_effect=None):
		def throw(msg, *a, **k):
			raise frappe.ValidationError(msg)

		delete_doc = MagicMock(side_effect=delete_side_effect)
		with patch.object(frappe, "only_for", MagicMock(), create=True), patch.object(frappe, "throw", throw, create=True), \
			patch.object(frappe, "delete_doc", delete_doc, create=True), \
			patch.object(frappe, "get_cached_doc", MagicMock(return_value=frappe._dict(enabled=posting)), create=True), \
			patch(f"{MODULE}.legacy_warehouse_report", return_value=report):
			try:
				result = setup.delete_legacy_warehouses(confirmation)
			except frappe.ValidationError:
				result = None
		return result, delete_doc

	def test_only_warehouses_with_a_replacement_and_no_references_are_deleted(self):
		result, delete_doc = self._run(self.REPORT)
		self.assertEqual(result["deleted"], ["A Raw - SSPP", "A Boiled - SSPP", "D Raw - SSPP"])
		self.assertEqual([c.args for c in delete_doc.call_args_list], [("Warehouse", n) for n in result["deleted"]])
		self.assertEqual([k["warehouse"] for k in result["kept"]], ["B Raw - SSPP", "C Raw - SSPP"])

	def test_a_warehouse_that_anything_refers_to_is_kept_and_reported_with_the_reason(self):
		result, _ = self._run(self.REPORT)
		self.assertEqual(result["kept"][0]["blocked_by"], ["1 stock ledger entries"])

	def test_the_exact_confirmation_phrase_is_required(self):
		for phrase in ("", "yes", "disable legacy warehouses", "Delete Legacy Warehouses now"):
			result, delete_doc = self._run(self.REPORT, confirmation=phrase)
			self.assertIsNone(result)
			delete_doc.assert_not_called()

	def test_it_is_refused_while_stock_posting_is_enabled(self):
		result, delete_doc = self._run(self.REPORT, posting=1)
		self.assertIsNone(result)
		delete_doc.assert_not_called()

	def test_nothing_is_deleted_when_every_warehouse_is_blocked(self):
		result, delete_doc = self._run([self.REPORT[2], self.REPORT[3]])
		self.assertEqual(result["deleted"], [])
		delete_doc.assert_not_called()

	def test_only_the_legacy_report_decides_which_warehouses_are_touched(self):
		result, delete_doc = self._run([])
		self.assertEqual((result["deleted"], result["kept"]), ([], []))
		delete_doc.assert_not_called()

	def test_a_failure_of_the_delete_itself_is_not_hidden(self):
		def fail(*a, **k):
			raise frappe.LinkExistsError("linked")

		with self.assertRaises(frappe.LinkExistsError):
			throw_free = None
			with patch.object(frappe, "only_for", MagicMock(), create=True), patch.object(frappe, "delete_doc", MagicMock(side_effect=fail), create=True), \
				patch.object(frappe, "get_cached_doc", MagicMock(return_value=frappe._dict(enabled=0)), create=True), \
				patch(f"{MODULE}.legacy_warehouse_report", return_value=self.REPORT[:1]):
				setup.delete_legacy_warehouses(setup.DELETE_CONFIRMATION)


class TestRetireLegacyWarehouses(unittest.TestCase):
	def test_a_warehouse_without_a_shared_replacement_is_not_safe(self):
		self.assertEqual(setup.legacy_safety({}, {"stock_ledger_entries": 0}, False), ["its physical location has no shared warehouse yet"])

	def test_any_reference_makes_it_unsafe_and_is_named(self):
		reasons = setup.legacy_safety({}, {"stock_ledger_entries": 2, "bag_ledger_entries": 0, "quality_checks_naming_it": 1}, True)
		self.assertEqual(reasons, ["2 stock ledger entries", "1 quality checks naming it"])

	def test_a_clean_warehouse_with_a_shared_replacement_is_safe(self):
		self.assertEqual(setup.legacy_safety({}, {"stock_ledger_entries": 0, "bins_with_stock": 0}, True), [])

	def _run(self, report, confirmation=setup.RETIRE_CONFIRMATION, posting=0):
		throw_calls = []

		def throw(msg, *a, **k):
			throw_calls.append(msg)
			raise frappe.ValidationError(msg)

		db = MagicMock()
		with patch.object(frappe, "only_for", MagicMock(), create=True), patch.object(frappe, "throw", throw, create=True), \
			patch.object(frappe, "db", db, create=True), patch.object(frappe, "delete_doc", MagicMock(), create=True) as delete_doc, \
			patch.object(frappe, "get_cached_doc", MagicMock(return_value=frappe._dict(enabled=posting)), create=True), \
			patch(f"{MODULE}.legacy_warehouse_report", return_value=report):
			try:
				result = setup.retire_legacy_warehouses(confirmation)
			except frappe.ValidationError:
				result = None
		return result, db, delete_doc

	REPORT = [
		{"name": "A Raw - SSPP", "disabled": 0, "safe_to_disable": True, "blocked_by": []},
		{"name": "B Raw - SSPP", "disabled": 0, "safe_to_disable": False, "blocked_by": ["1 stock ledger entries"]},
		{"name": "C Raw - SSPP", "disabled": 1, "safe_to_disable": False, "blocked_by": []},
	]

	def test_only_the_safe_warehouses_are_disabled_and_none_is_deleted(self):
		result, db, delete_doc = self._run(self.REPORT)
		self.assertEqual(result["disabled"], ["A Raw - SSPP"])
		self.assertEqual(result["kept"], [{"warehouse": "B Raw - SSPP", "blocked_by": ["1 stock ledger entries"]}])
		db.set_value.assert_called_once_with("Warehouse", "A Raw - SSPP", "disabled", 1)
		delete_doc.assert_not_called()

	def test_the_exact_confirmation_phrase_is_required(self):
		for phrase in ("", "yes", "Disable Legacy Warehouses please"):
			result, db, _ = self._run(self.REPORT, confirmation=phrase)
			self.assertIsNone(result)
			db.set_value.assert_not_called()

	def test_it_is_refused_while_stock_posting_is_enabled(self):
		result, db, _ = self._run(self.REPORT, posting=1)
		self.assertIsNone(result)
		db.set_value.assert_not_called()

	def test_apply_plan_never_runs_a_retirement_step(self):
		plan = {"plan_hash": "h", "posting_enabled": 0, "blocked": [], "steps": [
			{"id": "legacy:A Raw - SSPP", "kind": "Warehouse", "name": "A Raw - SSPP", "action": setup.RETIRE, "values": {}, "depends_on": [], "note": ""}]}
		with patch.object(frappe, "only_for", MagicMock(), create=True), patch(f"{MODULE}.build_plan", return_value=plan), \
			patch(f"{MODULE}._run_step") as run_step:
			result = setup.apply_plan("h")
		run_step.assert_not_called()
		self.assertEqual(result, {"applied": [], "skipped_missing_dependency": []})


class TestApprovedFile(unittest.TestCase):
	NINE_LOCATIONS = [
		"SSPP GODOWN", "SSPP GALI", "SSPP OPEN GODOWN",
		"RGFP MAIN GODOWN", "RGFP GALI", "RGFP CHALAN",
		"LGI PLANT", "LGI NEW PLANT", "LGI ECO STAND PLANT",
	]

	def test_shipped_file_holds_exactly_the_nine_physical_locations_and_no_unit(self):
		warehouses = setup.load_approved()["warehouses"]
		self.assertEqual([e["location"] for e in warehouses], self.NINE_LOCATIONS)  # each once, in the confirmed order
		self.assertTrue(all(set(e) == {"location"} for e in warehouses))  # shared: no operating unit named
		self.assertEqual(len({e["location"] for e in warehouses}), 9)

	CONFIRMED_ITEMS = [
		("paddy", "PADDY", "Paddy", "Raw Material"),
		("raw_rice", "RAW-RICE", "Raw Rice", "Products"),
		("boiled_rice", "BOILED-RICE", "Boiled Rice", "Products"),
		("by_product", "RICE-BRAN", "Rice Bran", "Products"),
		("by_product", "HUSK", "Husk", "Products"),
		("by_product", "MURI-RICE", "Muri Rice", "Products"),
	]

	def test_shipped_file_holds_exactly_the_six_confirmed_items(self):
		items = setup.load_approved()["items"]
		self.assertEqual([(e["role"], e["item_code"], e["item_name"], e["item_group"]) for e in items], self.CONFIRMED_ITEMS)
		roles = [e["role"] for e in items]
		self.assertEqual((roles.count("paddy"), roles.count("raw_rice"), roles.count("boiled_rice"), roles.count("by_product")), (1, 1, 1, 3))
		self.assertEqual(len({e["item_code"] for e in items}), 6)
		for entry in items:  # the schema the planner reads, nothing else (no rate or price keys)
			self.assertEqual(set(entry), {"role", "item_code", "item_name", "item_group"})

	def test_confirmed_items_plan_as_batch_tracked_quintal_items_without_rates_and_with_three_by_products(self):
		plan = setup.plan_from_snapshot(fully_configured(), setup.load_approved())
		items = [s for s in plan["steps"] if s["kind"] == "Item"]
		self.assertEqual(len(items), 6)
		for step in items:
			self.assertEqual(step["action"], "create")
			self.assertEqual((step["values"]["stock_uom"], step["values"]["has_batch_no"], step["values"]["is_stock_item"]), ("Quintal", 1, 1))
			self.assertFalse([k for k in step["values"] if "rate" in k or "price" in k])
		by_product_updates = [s["values"]["by_product_item"] for s in plan["steps"] if s["id"].startswith("settings:by_product:")]
		self.assertEqual(by_product_updates, ["RICE-BRAN", "HUSK", "MURI-RICE"])
		self.assertEqual(plan["pending"], [])
		self.assertEqual(plan["blocked"], [])

	def test_the_nine_locations_plan_as_nine_shared_warehouses_under_their_own_legal_company(self):
		plan = setup.plan_from_snapshot(fully_configured(), setup.load_approved())
		warehouses = [s for s in plan["steps"] if s["kind"] == "Warehouse"]
		self.assertEqual(len(warehouses), 9)
		self.assertEqual({s["action"] for s in warehouses}, {"create"})
		self.assertEqual(plan["blocked"], [])
		self.assertEqual(len({s["name"] for s in warehouses}), 9)  # distinct warehouse names
		for step in warehouses:
			self.assertNotIn("operating_unit", step["values"])  # Raw and Boiled share it
			abbr = step["values"]["physical_location"].split(" ")[0]
			self.assertEqual(step["values"]["company"], LEGAL_COMPANIES[abbr])  # the legal Company of the location


if __name__ == "__main__":
	unittest.main()
