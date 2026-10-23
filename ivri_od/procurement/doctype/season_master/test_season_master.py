# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

import unittest
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from ivri_od.procurement.doctype.season_master.season_master import (
	SeasonMaster,
	get_season_code,
	get_season_for_date,
)


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestSeasonMaster(IntegrationTestCase):
	"""
	Integration tests for SeasonMaster.
	Use this class for testing interactions between multiple components.
	"""

	pass


class TestSeasonMasterNoDB(unittest.TestCase):
	"""Mocked tests: no site, no database."""

	def setUp(self):
		frappe.local.lang = "en"

		def throw(msg, *args, **kwargs):
			raise frappe.ValidationError(msg)

		self.db = MagicMock()
		self.db.get_value.return_value = None
		for name, value in (("throw", throw), ("db", self.db)):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def _doc(self, has_field=True, **values):
		doc = SeasonMaster.__new__(SeasonMaster)
		doc.meta = MagicMock()  # meta is a cached_property, so this skips the database
		doc.meta.has_field.return_value = has_field
		doc.name, doc.crop_season, doc.year = "Kharif 2025", "Kharif", " 2025 "
		doc.season_code, doc.start_date, doc.end_date = "", None, None
		for key, value in values.items():
			setattr(doc, key, value)
		return doc

	def test_season_name_and_code_filled_from_type_and_year(self):
		doc = self._doc()
		doc.before_validate()
		self.assertEqual(doc.season_name, "Kharif 2025")
		self.assertEqual(doc.season_code, "K25")

	def test_year_name_and_code_follow_start_date(self):
		for crop, start, year, code in (("Rabi", "2026-05-01", "2025", "R25"), ("Kharif", "2025-11-01", "2025", "K25")):
			doc = self._doc(crop_season=crop, year="", start_date=start)
			doc.before_validate()
			self.assertEqual((doc.year, doc.season_name, doc.season_code), (year, f"{crop} {year}", code))

	def test_typed_season_code_is_replaced(self):
		doc = self._doc(season_code="K99", start_date="2025-06-01")
		doc.before_validate()
		self.assertEqual(doc.season_code, "K25")

	def test_year_is_set_before_naming_on_insert(self):
		doc = self._doc(crop_season="Rabi", year="", start_date="2026-05-01")
		doc.before_insert()
		self.assertEqual(doc.year, "2025")

	def test_season_created_in_code_without_start_date_keeps_year(self):
		doc = self._doc(year="2024")
		doc.before_insert()
		self.assertEqual((doc.year, doc.season_code), ("2024", "K24"))

	def test_no_code_without_season_type(self):
		doc = self._doc(name="Kharif 2025-26", crop_season=None, year="2025-26")
		doc.before_validate()
		self.assertEqual(doc.season_code, "")
		doc.validate()  # empty code is not checked for duplicates
		self.db.get_value.assert_not_called()

	def _saved(self, **values):
		doc = self._doc(**values)
		doc._doc_before_save = frappe._dict(crop_season="Kharif", year="2025")
		doc.is_new = lambda: False
		doc.before_validate()
		return doc

	def test_saved_season_cannot_change_year_or_type(self):
		for values in ({"start_date": "2026-06-01", "end_date": "2026-12-31"}, {"crop_season": "Rabi"}):
			with self.assertRaises(frappe.ValidationError) as ctx:
				self._saved(**values).validate()
			self.assertIn("Create a new Season Master", str(ctx.exception))

	def test_saved_season_can_add_dates_in_its_year(self):
		doc = self._saved(start_date="2025-06-01", end_date="2025-12-31")
		doc.validate()
		self.assertEqual((doc.year, doc.season_code), ("2025", "K25"))

	def test_valid_dates_pass(self):
		self._doc(season_code="K25", start_date="2025-10-01", end_date="2026-03-31").validate()

	def test_invalid_dates_are_blocked(self):
		for start, end in (("2025-10-01", None), ("2026-03-31", "2025-10-01")):
			with self.assertRaises(frappe.ValidationError):
				self._doc(season_code="K25", start_date=start, end_date=end).validate()

	def test_overlapping_season_is_blocked(self):
		self.db.get_value.side_effect = lambda doctype, filters, field: (
			"Rabi 2025" if "start_date" in filters else None
		)
		doc = self._doc(season_code="K25", start_date="2025-10-01", end_date="2026-03-31")
		with self.assertRaises(frappe.ValidationError) as ctx:
			doc.validate()
		self.assertIn("Rabi 2025", str(ctx.exception))

	def test_duplicate_season_code_is_blocked(self):
		self.db.get_value.return_value = "Kharif 2026"
		with self.assertRaises(frappe.ValidationError):
			self._doc(season_code="K25").validate()

	def test_before_migrate_nothing_new_runs(self):
		doc = self._doc(has_field=False, season_code="", start_date="2026-03-31", end_date="2025-10-01")
		doc.before_validate()
		doc.validate()
		self.assertEqual(doc.season_code, "")
		self.assertEqual(doc.year, "2025")
		self.db.get_value.assert_not_called()

	def test_lookups_before_migrate(self):
		self.db.has_column.return_value = False
		self.assertIsNone(get_season_for_date("2025-11-01"))
		self.assertEqual(get_season_code("Rabi 2025"), "R25")
		self.assertEqual(get_season_code(None), "")

	def test_configured_code_used_after_migrate(self):
		self.db.has_column.return_value = True
		self.db.get_value.return_value = "k25a"
		self.assertEqual(get_season_code("Kharif 2025"), "K25A")
