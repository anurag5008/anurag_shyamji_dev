# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement.doctype.chhatni.chhatni import Chhatni, get_chhatni_preview, pass_net_weight

ENTRY_MODULE = "ivri_od.procurement.doctype.entry.entry"
DOCTYPE_DIR = os.path.dirname(os.path.dirname(__file__))
TP_FIELDS = [
	"tp_section",
	"season",
	"ppc_name",
	"tp_no",
	"column_break_tp",
	"tp_quantity",
	"pass_unique_key",
	"transit_pass_no",
	"pacs_name",
]
RESULT_FIELDS = ["net_weight", "chhatni_kg", "chhatni_qt", "received_chhatni_pct"]
ENTRY_DETAIL_FIELDS = ["entry_details_section", "agent_name", "entry_quantity", "entry_price_per_quintal", "total_amount"]


def _load(doctype_folder):
	with open(os.path.join(DOCTYPE_DIR, doctype_folder, f"{doctype_folder}.json")) as f:
		return json.load(f)


class TestChhatniDocTypeNoDB(unittest.TestCase):
	"""DocType definition checks: no site, no database."""

	@classmethod
	def setUpClass(cls):
		cls.chhatni = _load("chhatni")
		cls.entry = _load("entry")
		cls.fields = {f["fieldname"]: f for f in cls.chhatni["fields"]}

	def test_transit_pass_section_matches_entry(self):
		entry_fields = {f["fieldname"]: f for f in self.entry["fields"]}
		for fieldname in TP_FIELDS:
			self.assertEqual(self.fields[fieldname], entry_fields[fieldname], fieldname)
		order = self.chhatni["field_order"]
		self.assertEqual(order[order.index("tp_section") : order.index("pacs_name") + 1], TP_FIELDS)

	def test_entry_details_are_not_included(self):
		for fieldname in ENTRY_DETAIL_FIELDS:
			self.assertNotIn(fieldname, self.fields)

	def test_chhatni_rate_field(self):
		field = self.fields["chhatni_kg_per_qtl"]
		self.assertEqual(field["label"], "Chhatni (Kg per Qtl)")
		self.assertEqual((field["fieldtype"], field["reqd"], field["non_negative"]), ("Float", 1, 1))
		self.assertEqual(self.fields["chhatni_section"]["label"], "Chhatni")

	def test_result_fields_are_read_only_after_rate(self):
		order = self.chhatni["field_order"]
		self.assertLess(order.index("chhatni_kg_per_qtl"), min(order.index(f) for f in RESULT_FIELDS))
		labels = [self.fields[f]["label"] for f in RESULT_FIELDS]
		self.assertEqual(labels, ["Net Weight (QT)", "Chhatni (KG)", "Chhatni (QT)", "Received Chhatni %"])
		for fieldname in RESULT_FIELDS:
			self.assertEqual(self.fields[fieldname]["read_only"], 1, fieldname)

	def test_kg_and_qt_hidden_but_stored(self):
		for fieldname in ("chhatni_kg", "chhatni_qt"):
			self.assertEqual(self.fields[fieldname].get("hidden"), 1, fieldname)
			self.assertEqual(self.fields[fieldname]["fieldtype"], "Float", fieldname)  # still a stored column
		for fieldname in ("net_weight", "received_chhatni_pct", "chhatni_kg_per_qtl"):
			self.assertFalse(self.fields[fieldname].get("hidden"), fieldname)

	def test_definition_is_complete(self):
		self.assertEqual(sorted(self.fields), sorted(self.chhatni["field_order"]))
		self.assertEqual((self.chhatni["name"], self.chhatni["module"]), ("Chhatni", "Procurement"))
		self.assertEqual(self.fields["naming_series"]["options"], "CH-.YYYY.-.#####")
		self.assertEqual(self.chhatni["permissions"], self.entry["permissions"])

	def test_discoverable_in_procurement_workspace_and_sidebar(self):
		from ivri_od.procurement.procurement_workspace import WORKSPACE_CARDS

		receipt = dict(WORKSPACE_CARDS)["Receipt & GRN"]
		self.assertIn(("Chhatni", "DocType"), receipt)
		app_dir = os.path.dirname(os.path.dirname(DOCTYPE_DIR))
		with open(os.path.join(app_dir, "workspace_sidebar", "procurement.json")) as f:
			links = [item.get("link_to") for item in json.load(f)["items"]]
		self.assertEqual(links.index("Chhatni"), links.index("Entry") + 1)


class TestChhatniLogicNoDB(unittest.TestCase):
	"""Transit Pass logic reused from Entry: no site, no database."""

	ROW = {
		"pass_unique_key": "M051007-AGALPUR(S1050118)-K25-TP28",
		"transit_pass_no": "28",
		"quantity": 250,
		"pacs": " AGALPUR PACS ",
	}

	def setUp(self):
		frappe.local.lang = "en"

		def throw(msg, *args, **kwargs):
			raise frappe.ValidationError(msg)

		self.db = MagicMock()
		self.db.exists.return_value = True
		self.db.get_value.return_value = None  # no other Chhatni for this pass
		self.db.sql.return_value = [[280.0]]  # total WBM net weight of the pass
		self.msgprint = MagicMock()
		# flt(value, precision) reads the rounding method from System Settings; use Frappe's default.
		settings = MagicMock(return_value=None)
		for name, value in (
			("throw", throw),
			("db", self.db),
			("msgprint", self.msgprint),
			("get_system_settings", settings),
		):
			patcher = patch.object(frappe, name, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def _doc(self, **values):
		doc = Chhatni.__new__(Chhatni)
		doc.season, doc.ppc_name, doc.tp_no = "Kharif 2025", "S1050118", " 28 "
		doc.pass_unique_key = doc.transit_pass_no = doc.pacs_name = ""
		doc.tp_quantity, doc.chhatni_kg_per_qtl = 0, 4
		doc.name = None
		for key, value in values.items():
			setattr(doc, key, value)
		return doc

	def test_validate_fetches_transit_pass_like_entry(self):
		doc = self._doc()
		with patch(f"{ENTRY_MODULE}.get_transit_pass_for_ppc_and_tp_no", return_value=self.ROW) as lookup:
			doc.validate()
		lookup.assert_called_once_with("S1050118", "28", season="Kharif 2025")
		self.assertEqual(doc.pass_unique_key, self.ROW["pass_unique_key"])
		self.assertEqual((doc.tp_no, doc.transit_pass_no, doc.tp_quantity), ("28", "28", 250))
		self.assertEqual(doc.pacs_name, "AGALPUR PACS")
		self.assertEqual(doc.chhatni_kg_per_qtl, 4)

	def _validated(self, **values):
		doc = self._doc(**values)
		with patch(f"{ENTRY_MODULE}.get_transit_pass_for_ppc_and_tp_no", return_value=self.ROW):
			doc.validate()
		return doc

	def test_example_280_qt_at_4_kg_per_qtl(self):
		doc = self._validated()
		self.assertEqual(
			(doc.net_weight, doc.chhatni_kg, doc.chhatni_qt, doc.received_chhatni_pct), (280.0, 1120.0, 11.2, 4.48)
		)

	def test_zero_tp_quantity_gives_zero_percent(self):
		row = dict(self.ROW, quantity=0)
		doc = self._doc()
		with patch(f"{ENTRY_MODULE}.get_transit_pass_for_ppc_and_tp_no", return_value=row):
			doc.validate()
		self.assertEqual((doc.chhatni_kg, doc.chhatni_qt, doc.received_chhatni_pct), (1120.0, 11.2, 0.0))
		self.assertEqual(self.db.sql.call_args.args[1], self.ROW["pass_unique_key"])
		self.msgprint.assert_not_called()

	def test_zero_or_missing_net_weight_saves_zeros_and_informs(self):
		for net in (0, None, -5):
			self.msgprint.reset_mock()
			self.db.sql.return_value = [[net]]
			doc = self._validated()
			self.assertEqual((doc.net_weight, doc.chhatni_kg, doc.chhatni_qt, doc.received_chhatni_pct), (0, 0, 0, 0))
			self.assertEqual(self.msgprint.call_args.kwargs["title"], "Net Weight Not Found")

	def test_second_chhatni_for_same_pass_is_blocked(self):
		self.db.get_value.return_value = "CH-2026-00001"
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._validated(name="CH-2026-00002")
		self.assertIn("already exists", str(ctx.exception))
		filters = self.db.get_value.call_args.args[1]
		self.assertEqual(filters["name"], ["!=", "CH-2026-00002"])

	def test_rate_change_recalculates_on_save(self):
		doc = self._validated(chhatni_kg_per_qtl=4.5)
		self.assertEqual((doc.chhatni_kg, doc.chhatni_qt, doc.received_chhatni_pct), (1260.0, 12.6, 5.04))

	def test_pass_net_weight_without_key(self):
		self.assertEqual(pass_net_weight(" "), 0.0)
		self.db.sql.assert_not_called()

	def test_preview_checks_permission_and_calculates(self):
		with patch.object(frappe, "has_permission", create=True) as has_permission:
			res = get_chhatni_preview("KEY", "4", "250")
		has_permission.assert_called_once_with("Chhatni", "read", throw=True)
		self.assertEqual(res, {"net_weight": 280.0, "chhatni_kg": 1120.0, "chhatni_qt": 11.2, "received_chhatni_pct": 4.48})
		with patch.object(frappe, "has_permission", create=True):
			self.assertEqual(get_chhatni_preview("KEY", "4")["received_chhatni_pct"], 0.0)  # no TP Quantity

	def test_validate_blocks_like_entry(self):
		cases = (
			({"season": ""}, self.ROW, True, "Season is required"),
			({"tp_no": ""}, self.ROW, True, "PPC and TP No are required"),
			({}, None, True, "No PPAS Transit Pass found for Season"),
			({}, self.ROW, False, "No PPAS Transit Pass found for Pass Unique Key"),
		)
		for values, row, key_exists, message in cases:
			self.db.exists.return_value = key_exists
			with patch(f"{ENTRY_MODULE}.get_transit_pass_for_ppc_and_tp_no", return_value=row):
				with self.assertRaises(frappe.ValidationError) as ctx:
					self._doc(**values).validate()
			self.assertIn(message, str(ctx.exception))

	def test_no_entry_quantity_or_grn_logic(self):
		for name in ("_validate_available_quantity", "_update_total_amount", "_sync_grn_entry_details", "on_update"):
			self.assertFalse(hasattr(Chhatni, name), name)
