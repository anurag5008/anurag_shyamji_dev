# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Quality Check Unloading Point as a Warehouse link. Mocked tests: no site, no database."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.document import Document

from ivri_od.procurement import stock_posting as sp
from ivri_od.procurement.doctype.quality_check.quality_check import QualityCheck

MODULE = "ivri_od.procurement.stock_posting"
QC_JSON = os.path.join(os.path.dirname(__file__), "..", "doctype", "quality_check", "quality_check.json")
MAPPED = frappe._dict(name="GODOWN Boiled - SSPP", operating_unit="M051007", physical_location="SSPP GODOWN", is_group=0, disabled=0)


def qc(unloading_point="GODOWN Boiled - SSPP", new=False, farmer=0, **extra):
	doc = QualityCheck.__new__(QualityCheck)
	doc.__dict__.update(
		{"name": "QC-2026-116", "unloading_point": unloading_point, "is_farmer_or_agent": farmer, "__islocal": 1 if new else 0, **extra}
	)
	return doc


class UnloadingTestCase(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = MagicMock()
		self.stored = "Warehouse 1"
		self.warehouses = {}  # name -> row for frappe.db.get_value("Warehouse", name, [...])
		self.db.get_value.side_effect = self._get_value
		self.db.exists.side_effect = lambda doctype, name=None: doctype == "Warehouse" and name in self.warehouses

		def throw(msg, *a, **k):
			raise frappe.ValidationError(msg)

		# flt(x, 3) reads the rounding method from System Settings; no site is bound, so use the default.
		for name, value in (
			("throw", throw), ("db", self.db), ("msgprint", MagicMock()), ("bold", lambda x: x),
			("get_system_settings", lambda key: None),
		):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def _get_value(self, doctype, filters=None, fieldname=None, *a, **k):
		if doctype == "Quality Check":
			return self.stored
		if doctype == "Warehouse":
			return self.warehouses.get(filters)
		return None


class TestFieldDefinition(unittest.TestCase):
	def test_unloading_point_is_a_warehouse_link_limited_to_the_physical_warehouses(self):
		with open(QC_JSON) as handle:
			field = next(f for f in json.load(handle)["fields"] if f["fieldname"] == "unloading_point")
		self.assertEqual((field["fieldtype"], field["options"]), ("Link", "Warehouse"))
		filters = json.loads(field["link_filters"])
		self.assertIn(["Warehouse", "physical_location", "is", "set"], filters)
		self.assertNotIn(["Warehouse", "operating_unit", "is", "set"], filters)  # Raw and Boiled share the warehouse
		self.assertIn(["Warehouse", "is_group", "=", 0], filters)
		self.assertIn(["Warehouse", "disabled", "=", 0], filters)
		# the existing rules for the field are untouched: required only when it is not a farmer / agent load
		self.assertEqual(field["depends_on"], "eval:!doc.is_farmer_or_agent")
		self.assertEqual(field["mandatory_depends_on"], "eval:!doc.is_farmer_or_agent")


class TestLegacyRecords(UnloadingTestCase):
	"""The 10 saved Quality Checks hold free text. They must stay editable and their value must not change."""

	def test_unchanged_free_text_on_a_saved_record_is_legacy(self):
		self.assertTrue(qc("Warehouse 1")._legacy_unloading_point())

	def test_changed_value_new_record_or_real_warehouse_is_not_legacy(self):
		self.assertFalse(qc("Warehouse 2")._legacy_unloading_point())  # edited away from the stored text
		self.assertFalse(qc("Warehouse 1", new=True)._legacy_unloading_point())
		self.warehouses["Warehouse 1"] = MAPPED
		self.assertFalse(qc("Warehouse 1")._legacy_unloading_point())  # it is a warehouse now: normal validation
		self.assertFalse(qc("")._legacy_unloading_point())

	def run_links(self, doc, raises=False):
		seen = {}

		def fake(self_):
			seen["during"] = self_.unloading_point
			if raises:
				raise frappe.ValidationError("other link invalid")

		with patch.object(Document, "_validate_links", fake):
			try:
				doc._validate_links()
			except frappe.ValidationError:
				seen["raised"] = True
		return seen

	def test_legacy_value_is_hidden_from_link_validation_and_restored_afterwards(self):
		doc = qc("Warehouse 1")
		seen = self.run_links(doc)
		self.assertIsNone(seen["during"])  # the other links are validated without it
		self.assertEqual(doc.unloading_point, "Warehouse 1")  # the stored value is untouched

	def test_value_is_restored_even_when_another_link_is_invalid_and_that_error_still_surfaces(self):
		doc = qc("Warehouse 1")
		seen = self.run_links(doc, raises=True)
		self.assertTrue(seen.get("raised"))
		self.assertEqual(doc.unloading_point, "Warehouse 1")

	def test_a_new_or_changed_value_is_validated_like_any_other_link(self):
		self.assertEqual(self.run_links(qc("Warehouse 2"))["during"], "Warehouse 2")
		self.assertEqual(self.run_links(qc("GODOWN Boiled - SSPP", new=True))["during"], "GODOWN Boiled - SSPP")


class TestWarehouseRule(UnloadingTestCase):
	def check(self, doc):
		doc._validate_unloading_warehouse()

	def refuses(self, doc):
		with self.assertRaises(frappe.ValidationError):
			self.check(doc)

	def test_a_mapped_enabled_warehouse_is_accepted(self):
		self.warehouses["GODOWN Boiled - SSPP"] = MAPPED
		self.check(qc("GODOWN Boiled - SSPP", new=True))

	def test_free_text_that_is_not_a_warehouse_is_refused_when_new_or_changed(self):
		self.refuses(qc("Warehouse 2"))
		self.refuses(qc("Godown X", new=True))

	def test_a_shared_physical_warehouse_without_an_operating_unit_is_accepted(self):
		self.warehouses["GODOWN - SSPP"] = frappe._dict(MAPPED, name="GODOWN - SSPP", operating_unit=None)
		self.check(qc("GODOWN - SSPP", new=True))
		self.warehouses["GALI - SSPP"] = frappe._dict(MAPPED, name="GALI - SSPP", operating_unit="")
		self.check(qc("GALI - SSPP", new=True))

	def test_an_older_per_unit_warehouse_is_still_accepted_until_it_is_retired(self):
		self.warehouses["GODOWN Raw - SSPP"] = frappe._dict(MAPPED, name="GODOWN Raw - SSPP", operating_unit="M050414")
		self.check(qc("GODOWN Raw - SSPP", new=True))

	def test_unmapped_group_or_disabled_warehouse_is_refused(self):
		for override in ({"physical_location": ""}, {"physical_location": None}, {"is_group": 1}, {"disabled": 1}):
			self.warehouses["Stores - SSPP"] = frappe._dict(MAPPED, name="Stores - SSPP", **override)
			self.refuses(qc("Stores - SSPP", new=True))

	def test_unchanged_legacy_text_is_left_alone(self):
		self.check(qc("Warehouse 1"))  # no error: historical value, not modified

	def test_farmer_or_agent_loads_and_blank_values_are_not_checked_here(self):
		self.check(qc("anything", new=True, farmer=1))
		self.check(qc("", new=True))  # the existing mandatory rule handles blank


class TestPostingUsesTheQcWarehouse(UnloadingTestCase):
	def test_a_valid_qc_warehouse_is_found_only_when_mapped_enabled_and_not_a_group(self):
		self.warehouses[None] = None

		def get_value(doctype, filters=None, fieldname=None, *a, **k):
			self.last_filters = filters
			return "GODOWN Boiled - SSPP" if filters.get("name") == "GODOWN Boiled - SSPP" else None

		self.db.get_value.side_effect = get_value
		self.assertEqual(sp._unloading_warehouse("GODOWN Boiled - SSPP"), "GODOWN Boiled - SSPP")
		self.assertEqual(self.last_filters["physical_location"], ["is", "set"])
		self.assertNotIn("operating_unit", self.last_filters)  # Raw and Boiled share the physical warehouse
		self.assertEqual((self.last_filters["is_group"], self.last_filters["disabled"]), (0, 0))
		self.assertEqual(sp._unloading_warehouse("Warehouse 1"), "")  # legacy free text: no constraint
		self.assertEqual(sp._unloading_warehouse(""), "")
		self.assertEqual(sp._unloading_warehouse(None), "")

	def test_posting_must_go_to_the_warehouse_the_quality_check_names(self):
		grn = frappe._dict(unloading_warehouse="GODOWN Boiled - SSPP")
		self.assertEqual(sp.unloading_point_errors(grn, MAPPED), [])
		other = frappe._dict(MAPPED, name="GALI Boiled - SSPP")
		errors = sp.unloading_point_errors(grn, other)
		self.assertEqual(len(errors), 1)
		self.assertIn("GODOWN Boiled - SSPP", errors[0])

	def test_legacy_or_missing_qc_warehouse_puts_no_constraint_on_the_choice(self):
		for named in ("", None):
			self.assertEqual(sp.unloading_point_errors(frappe._dict(unloading_warehouse=named), MAPPED), [])
		self.assertEqual(sp.unloading_point_errors(frappe._dict(), None), [])

	def test_eligibility_includes_the_unloading_rule(self):
		from ivri_od.procurement.tests.test_stock_posting import ITEM, MILL, WAREHOUSE, WBM, grn

		g = grn(unloading_warehouse="GALI Boiled - SSPP")  # QC says GALI, the chosen warehouse is GODOWN
		errors = sp.grn_posting_errors(g, frappe._dict(WBM), MILL, ITEM, WAREHOUSE)
		self.assertTrue(any("Quality Check says" in e for e in errors))
		g = grn(unloading_warehouse=WAREHOUSE.name)
		self.assertEqual(sp.grn_posting_errors(g, frappe._dict(WBM), MILL, ITEM, WAREHOUSE), [])


# ---- the Unloading Point dropdown: no line that spells out the filters ----

import glob
import re
import subprocess
import shutil
from pathlib import Path

QC_JS = Path(__file__).resolve().parents[1] / "doctype" / "quality_check" / "quality_check.js"
LINK_JS = Path(frappe.__file__).resolve().parent / "public" / "js" / "frappe" / "form" / "controls" / "link.js"

HARNESS = r"""
const fs = require("fs");
const src = fs.readFileSync(process.argv.slice(-1)[0], "utf8");
const start = src.indexOf("function hide_unloading_point_filter_description(");
const end = src.indexOf("\n}\n", start);
if (start < 0) throw new Error("helper not found");
const hide = new Function(src.slice(start, end + 2) + "\nreturn hide_unloading_point_filter_description;")();
const text = async () => "Filters applied for Warehouse: Physical Location is set";
const unloading = { get_filter_description: text };
const vehicle = { get_filter_description: text };
const frm = { fields_dict: { unloading_point: unloading, vehicle_no: vehicle } };
(async () => {
	const before = await unloading.get_filter_description([["Warehouse", "disabled", "=", 0]]);
	hide(frm);
	const wrapped = unloading.get_filter_description;
	const after = await unloading.get_filter_description([["Warehouse", "disabled", "=", 0]]);
	hide(frm);  // a second call must not wrap again
	const again = unloading.get_filter_description === wrapped;
	const other = await vehicle.get_filter_description([]);
	hide({ fields_dict: {} });  // a form without the field: nothing to do, no error
	console.log(JSON.stringify({ before, after, again, other, flag: unloading._filter_description_hidden }));
})();
"""


def _node():
	found = shutil.which("node")
	if found:
		return found
	matches = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
	return matches[-1] if matches else None


@unittest.skipUnless(_node(), "Node is not installed")
class TestUnloadingPointDropdownHasNoFilterLine(unittest.TestCase):
	def test_the_unloading_point_control_no_longer_builds_the_filter_description(self):
		out = subprocess.run([_node(), "-e", HARNESS, str(QC_JS)], capture_output=True, text=True, check=True)
		result = json.loads(out.stdout)
		self.assertTrue(result["before"].startswith("Filters applied"))  # what Frappe would add at the end of the dropdown
		self.assertIsNone(result["after"])  # now nothing is added
		self.assertTrue(result["again"])  # idempotent: refreshing the form does not wrap it again
		self.assertTrue(result["flag"])

	def test_other_fields_keep_their_own_behaviour(self):
		out = subprocess.run([_node(), "-e", HARNESS, str(QC_JS)], capture_output=True, text=True, check=True)
		self.assertTrue(json.loads(out.stdout)["other"].startswith("Filters applied"))

	def test_the_form_applies_it_on_load_and_on_refresh(self):
		source = QC_JS.read_text()
		for handler in ("onload", "refresh"):
			body = re.search(rf"\n\t{handler}\(frm\) \{{(.*?)\n\t\}},", source, re.S).group(1)
			self.assertIn("hide_unloading_point_filter_description(frm);", body, handler)

	def test_the_override_only_touches_the_unloading_point_control(self):
		source = QC_JS.read_text()
		start = source.index("function hide_unloading_point_filter_description(")
		body = source[start: source.index("\n}\n", start)]
		self.assertEqual(re.findall(r"fields_dict\.(\w+)", body), ["unloading_point"])

	def test_it_relies_on_the_frappe_behaviour_it_was_written_for(self):
		"""If Frappe builds that line another way, this fails and the override needs another look."""
		link = LINK_JS.read_text()
		self.assertIn("await this.get_filter_description(filters)", link)
		self.assertRegex(link, r"if \(filter_string\) \{\s*r\.message\.push\(")

	def test_the_filters_themselves_are_not_touched(self):
		with open(QC_JSON) as handle:
			field = next(f for f in json.load(handle)["fields"] if f["fieldname"] == "unloading_point")
		self.assertEqual(
			json.loads(field["link_filters"]),
			[["Warehouse", "physical_location", "is", "set"], ["Warehouse", "is_group", "=", 0], ["Warehouse", "disabled", "=", 0]],
		)


if __name__ == "__main__":
	unittest.main()
