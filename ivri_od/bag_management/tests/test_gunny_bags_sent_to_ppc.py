# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Gunny Bags Sent to PPC: the approved shape of the DocType and the bag-count rule. No site, no database."""

import json
import unittest
from pathlib import Path

import ivri_od
from ivri_od.bag_management.doctype.gunny_bags_sent_to_ppc.gunny_bags_sent_to_ppc import bag_count_error

ROOT = Path(ivri_od.__file__).resolve().parent
DOCTYPE = json.loads((ROOT / "bag_management/doctype/gunny_bags_sent_to_ppc/gunny_bags_sent_to_ppc.json").read_text())
FIELDS = {f["fieldname"]: f for f in DOCTYPE["fields"]}
DATA_FIELDS = {k for k, f in FIELDS.items() if f["fieldtype"] not in ("Column Break", "Section Break")}


class TestBagCount(unittest.TestCase):
	def test_a_positive_whole_number_is_accepted(self):
		for ok in (1, 250, "40", 3.0):
			self.assertIsNone(bag_count_error(ok), ok)

	def test_zero_negative_fractional_and_non_numbers_are_refused(self):
		for bad in (0, -1, -250, 2.5, "x", None, ""):
			self.assertIsNotNone(bag_count_error(bad), bad)


class TestDocTypeShape(unittest.TestCase):
	def test_only_the_approved_fields_exist(self):
		self.assertEqual(DATA_FIELDS, {"issue_date", "operating_unit", "ppc", "district", "bags_sent", "amended_from"})
		self.assertNotIn("remarks", FIELDS)

	def test_it_is_submittable(self):
		self.assertEqual(DOCTYPE["is_submittable"], 1)

	def test_operating_unit_is_required_and_never_defaulted(self):
		unit = FIELDS["operating_unit"]
		self.assertEqual((unit["fieldtype"], unit["options"], unit.get("reqd")), ("Link", "Mill Master", 1))
		self.assertNotIn("default", unit)

	def test_ppc_is_a_required_link_to_ppc_master(self):
		self.assertEqual((FIELDS["ppc"]["fieldtype"], FIELDS["ppc"]["options"], FIELDS["ppc"].get("reqd")), ("Link", "PPC Master", 1))

	def test_district_is_read_only_and_fetched_from_the_ppc_district_field(self):
		district = FIELDS["district"]
		self.assertEqual((district["fetch_from"], district["read_only"], district["options"]), ("ppc.district", 1, "District Master"))

	def test_bags_are_a_required_whole_number_field(self):
		self.assertEqual((FIELDS["bags_sent"]["fieldtype"], FIELDS["bags_sent"].get("reqd"), FIELDS["bags_sent"].get("non_negative")), ("Int", 1, 1))

	def test_amend_points_back_at_this_doctype(self):
		self.assertEqual(FIELDS["amended_from"]["options"], DOCTYPE["name"])

	def test_only_system_manager_has_any_permission(self):
		perms = DOCTYPE["permissions"]
		self.assertEqual([p["role"] for p in perms], ["System Manager"])
		for right in ("read", "write", "create", "submit", "cancel", "amend"):
			self.assertEqual(perms[0].get(right), 1, right)

	def test_navigation_links_this_doctype_and_is_for_system_manager_only(self):
		ws = json.loads((ROOT / "bag_management/workspace/bag_management/bag_management.json").read_text())
		self.assertIn(("DocType", DOCTYPE["name"]), [(s["type"], s["link_to"]) for s in ws["shortcuts"]])
		self.assertEqual([r["role"] for r in ws["roles"]], ["System Manager"])
		sb = json.loads((ROOT / "workspace_sidebar/bag_management.json").read_text())
		self.assertIn(DOCTYPE["name"], [i["link_to"] for i in sb["items"]])
