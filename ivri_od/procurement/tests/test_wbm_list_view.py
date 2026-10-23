# Copyright (c) 2026, Profezzo and contributors

import json
import os
import shutil
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.patches.v1_0 import weigh_bridge_list_view_actual_truck_no as truck_patch
from ivri_od.patches.v1_0 import weigh_bridge_list_view_defaults as patch_module
from ivri_od.patches.v1_0 import weigh_bridge_list_view_final_columns as final_patch
from ivri_od.patches.v1_0 import weigh_bridge_list_view_quality_columns as quality_patch
from ivri_od.patches.v1_0 import weigh_bridge_list_view_show_tp_no as show_patch
from ivri_od.patches.v1_0 import weigh_bridge_list_view_tp_no as tp_no_patch

WBM_JSON = os.path.join(
	os.path.dirname(__file__), "..", "doctype", "weigh_bridge_measurement", "weigh_bridge_measurement.json"
)


def _meta():
	with open(WBM_JSON) as handle:
		return json.load(handle)


class TestWeighBridgeListViewConfig(unittest.TestCase):
	def setUp(self):
		self.meta = _meta()
		self.fields = {field["fieldname"]: field for field in self.meta["fields"]}

	def test_status_and_lot_no_labels(self):
		self.assertEqual(self.fields["tp_status"]["label"], "Status")
		self.assertEqual(self.fields["lot_no"]["label"], "Lot No")

	def test_fieldnames_types_and_statuses_unchanged(self):
		status = self.fields["tp_status"]
		self.assertEqual(status["fieldtype"], "Select")
		self.assertEqual(
			[option for option in status["options"].split("\n") if option],
			["TP Received", "TP Not Received", "Local Procurement", "Rice Dispatch"],
		)
		self.assertEqual(self.fields["lot_no"]["fieldtype"], "Data")
		self.assertEqual(self.fields["lot_no"]["read_only"], 1)

	def test_default_list_columns(self):
		in_list = {name for name, field in self.fields.items() if field.get("in_list_view")}
		self.assertEqual(
			in_list,
			{"rst_no", "transit_pass_no", "lot_no", "party_name", "truck_no_in_tp", "actual_truck_no", "net_weight",
				"quality_test", "tp_status", "date"},
		)

	def test_first_column_is_rst_no_and_default_sort_is_newest_first(self):
		self.assertEqual(self.meta["title_field"], "rst_no")
		self.assertEqual((self.meta["sort_field"], self.meta["sort_order"]), ("date", "DESC"))

	def test_standard_filters_are_kept(self):
		filters = {name for name, field in self.fields.items() if field.get("in_standard_filter")}
		self.assertEqual(
			filters,
			{"agent_name", "pass_unique_key", "party_name", "local_purchase_order", "rst_no",
				"quality_check", "slno_of_qc", "tp_status", "quality_test", "commodity", "gunny_type"},
		)

	def test_search_fields_are_kept(self):
		for name in ("pass_unique_key", "rst_no", "tp_status", "quality_check", "truck_no_in_tp"):
			self.assertIn(name, self.meta["search_fields"])

	def test_requested_order_uses_real_fields(self):
		for fieldname, _label in quality_patch.LIST_FIELDS + [(name, "") for name in quality_patch.REMOVED]:
			self.assertIn(fieldname, self.fields)
		self.assertEqual(
			[fieldname for fieldname, _ in quality_patch.LIST_FIELDS],
			["transit_pass_no", "lot_no", "party_name", "truck_no_in_tp", "actual_truck_no", "net_weight",
				"quality_test", "tp_status", "date"],
		)
		self.assertEqual(self.meta["title_field"], "rst_no")  # RST No stays the first (link) column

	def test_tp_no_is_the_existing_transit_pass_no_field_and_stays_read_only(self):
		field = self.fields["transit_pass_no"]
		self.assertEqual((field["fieldtype"], field["label"], field.get("read_only")), ("Data", "TP No", 1))
		self.assertEqual(quality_patch.LIST_FIELDS[0], ("transit_pass_no", "TP No"))
		self.assertNotIn("Transit Pass No", [f.get("label") for f in self.fields.values()])

	def test_tp_no_stays_right_before_lot_no(self):
		order = [fieldname for fieldname, _ in quality_patch.LIST_FIELDS]
		self.assertEqual(order.index("transit_pass_no") + 1, order.index("lot_no"))

	def test_quality_check_sl_no_is_not_a_default_column_but_stays_a_filter(self):
		self.assertFalse(self.fields["quality_check"].get("in_list_view"))
		self.assertEqual(self.fields["quality_check"].get("in_standard_filter"), 1)
		self.assertNotIn("quality_check", [fieldname for fieldname, _ in quality_patch.LIST_FIELDS])

	def test_quality_test_options_and_truck_no_in_tp(self):
		options = [option for option in self.fields["quality_test"]["options"].split("\n") if option]
		self.assertEqual(options, ["Pending QC", "Accepted", "Rejected", "Partially Accepted"])
		self.assertEqual(self.fields["truck_no_in_tp"]["label"], "Truck No in TP")

	def test_no_hidden_field_is_a_list_column(self):
		for name, field in self.fields.items():
			if field.get("in_list_view"):
				self.assertFalse(field.get("hidden"), name)
				self.assertNotIn(field["fieldtype"], ("Section Break", "Column Break", "Tab Break", "Table", "HTML"), name)

	def test_id_column_is_hidden(self):
		with open(WBM_JS) as handle:
			self.assertIn("hide_name_column: true", handle.read())

	def test_lot_no_field_is_separate_from_tp_no(self):
		self.assertNotEqual(self.fields["lot_no"]["fieldname"], self.fields["transit_pass_no"]["fieldname"])
		self.assertEqual(self.fields["lot_no"]["depends_on"], "eval:doc.tp_status=='Rice Dispatch'")


class TestWeighBridgeTPNoListPatch(unittest.TestCase):
	def setUp(self):
		self.db = MagicMock()
		self.get_doc = MagicMock()
		for patcher in (
			patch.object(frappe, "db", self.db, create=True),
			patch.object(frappe, "get_doc", self.get_doc, create=True),
			patch.object(frappe, "reload_doc", MagicMock(), create=True),
			patch.object(frappe, "clear_cache", MagicMock(), create=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def _saved_fields(self):
		return json.loads(self.db.set_value.call_args.args[3])

	def test_updates_the_existing_record_with_tp_no_before_lot_no(self):
		self.db.exists.return_value = True
		tp_no_patch.execute()
		self.assertEqual(self.db.set_value.call_args.args[:3], ("List View Settings", "Weigh Bridge Measurement", "fields"))
		order = [field["fieldname"] for field in self._saved_fields()]
		self.assertEqual(
			order,
			["date", "transit_pass_no", "lot_no", "net_weight", "party_name", "quality_check", "tp_status",
				"quality_test", "truck_no_in_tp"],
		)
		self.assertEqual(order.index("transit_pass_no") + 1, order.index("lot_no"))
		self.assertEqual({f["fieldname"]: f["label"] for f in self._saved_fields()}["transit_pass_no"], "TP No")
		self.get_doc.assert_not_called()

	def test_creates_the_record_when_missing(self):
		self.db.exists.return_value = False
		tp_no_patch.execute()
		payload = self.get_doc.call_args.args[0]
		self.assertEqual((payload["doctype"], payload["name"]), ("List View Settings", "Weigh Bridge Measurement"))
		self.assertEqual(json.loads(payload["fields"])[1]["fieldname"], "transit_pass_no")
		self.db.set_value.assert_not_called()

	def test_touches_no_weighment_records_or_user_settings(self):
		self.db.exists.return_value = True
		tp_no_patch.execute()
		self.db.sql.assert_not_called()
		self.assertEqual({call.args[0] for call in self.db.set_value.call_args_list}, {"List View Settings"})


WBM_DIR = os.path.join(os.path.dirname(__file__), "..", "doctype", "weigh_bridge_measurement")
WBM_JS = os.path.join(WBM_DIR, "weigh_bridge_measurement_list.js")
WBM_FORM_JS = os.path.join(WBM_DIR, "weigh_bridge_measurement.js")

_NODE_HARNESS = """
const fs = require('fs'), vm = require('vm');
const escape_html = (t) => String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const sandbox = { frappe: { listview_settings: {}, ui: { form: { on() {} } }, utils: { escape_html } }, __: (t) => t, flt: Number };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
const settings = sandbox.frappe.listview_settings['Weigh Bridge Measurement'];
const out = {
  add_fields: settings.add_fields,
  cells: JSON.parse(process.argv[2]).map((doc) => settings.formatters.party_name(doc.party_name, {}, doc)),
};
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestWeighBridgePartyNameDisplay(unittest.TestCase):
	"""The Party Name column: the stored Party Name, else the PPC Name. Display only."""

	def _cells(self, docs):
		done = subprocess.run(
			["node", "-e", _NODE_HARNESS, WBM_JS, json.dumps(docs)], capture_output=True, text=True, check=True
		)
		result = json.loads(done.stdout)
		self.assertIn("pacs_name", result["add_fields"])
		return result["cells"]

	@staticmethod
	def _text(cell):
		return cell.split(">", 1)[1].rsplit("<", 1)[0]

	def test_government_paddy_purchase_shows_the_ppc_name(self):
		cell = self._cells([{"party_name": None, "pacs_name": "KOTPADLAMPCS(S1200701)", "tp_status": "TP Received"}])[0]
		self.assertEqual(self._text(cell), "KOTPADLAMPCS(S1200701)")

	def test_rice_dispatch_shows_the_party_name(self):
		cell = self._cells([{"party_name": "MALMUNDA", "pacs_name": "", "tp_status": "Rice Dispatch"}])[0]
		self.assertEqual(self._text(cell), "MALMUNDA")

	def test_local_paddy_purchase_shows_the_party_name(self):
		cell = self._cells([{"party_name": "Some Farmer", "pacs_name": "", "tp_status": "Local Procurement"}])[0]
		self.assertEqual(self._text(cell), "Some Farmer")

	def test_party_name_wins_over_ppc_name_when_both_exist(self):
		cell = self._cells([{"party_name": "REAL PARTY", "pacs_name": "SOME PPC(S1)"}])[0]
		self.assertEqual(self._text(cell), "REAL PARTY")

	def test_ppc_is_read_from_the_pass_unique_key_when_pacs_name_is_empty(self):
		cells = self._cells([
			{"party_name": None, "pacs_name": "", "pass_unique_key": "M051007-BOBEYA(MY200703)-R25-TP295"},
			{"party_name": None, "pacs_name": None, "pass_unique_key": "M051007-G S DUNGURIPALI(S1050807)-K25-TP18"},
			{"party_name": None, "pacs_name": None, "pass_unique_key": "M051007-A-B CENTRE(S1)-K25-TP12-A"},
			{"party_name": None, "pacs_name": None, "pass_unique_key": "not a pass key"},
			{"party_name": None, "pacs_name": None, "pass_unique_key": None},
		])
		self.assertEqual(
			[self._text(cell) for cell in cells],
			["BOBEYA(MY200703)", "G S DUNGURIPALI(S1050807)", "A-B CENTRE(S1)", "", ""],
		)

	def test_pass_unique_key_is_fetched_for_the_list(self):
		with open(WBM_JS) as handle:
			self.assertIn('add_fields: ["pacs_name", "pass_unique_key"]', handle.read())

	def test_regression_tp_received_party_name_was_blank_after_refresh(self):
		"""The formatter used to sit in the form script, which Frappe loads only after a form is opened."""
		with open(WBM_JS) as handle:
			self.assertIn('frappe.listview_settings["Weigh Bridge Measurement"]', handle.read())
		with open(WBM_FORM_JS) as handle:
			self.assertNotIn("listview_settings", handle.read())

	def test_filter_buttons_are_kept(self):
		with open(WBM_JS) as handle:
			source = handle.read()
		for status in ("TP Not Received", "TP Received", "Rice Dispatch"):
			self.assertIn(f'["Weigh Bridge Measurement", "tp_status", "=", "{status}"]', source)

	def test_both_empty_shows_nothing_and_text_is_escaped(self):
		empty, tricky = self._cells([{"party_name": None, "pacs_name": None}, {"party_name": "<b>x</b>", "pacs_name": ""}])
		self.assertEqual(self._text(empty), "")
		self.assertNotIn("<b>", tricky)
		self.assertIn("&lt;b&gt;x&lt;/b&gt;", tricky)
		self.assertIn('title="Party Name:', tricky)


class TestQualityColumnsPatch(unittest.TestCase):
	def _run(self, exists=True):
		db = MagicMock()
		db.exists.return_value = exists
		meta = MagicMock()
		get_doc = MagicMock()
		with patch.object(frappe, "db", db, create=True), patch.object(
			frappe, "reload_doc", MagicMock(), create=True
		), patch.object(frappe, "get_meta", return_value=meta, create=True), patch.object(
			frappe, "get_doc", get_doc, create=True
		), patch.object(frappe, "clear_cache", MagicMock(), create=True), patch.object(
			quality_patch, "set_in_list_view_property"
		) as setter:
			quality_patch.execute()
		return db, meta, get_doc, setter

	def test_saves_the_clean_order(self):
		db, _, _, _ = self._run()
		saved = json.loads(db.set_value.call_args.args[3])
		self.assertEqual(
			[field["fieldname"] for field in saved],
			["transit_pass_no", "lot_no", "party_name", "truck_no_in_tp", "actual_truck_no", "net_weight",
				"quality_test", "tp_status", "date"],
		)
		self.assertEqual({f["fieldname"]: f["label"] for f in saved}["transit_pass_no"], "TP No")

	def test_switches_the_columns_on_and_quality_check_off(self):
		_, meta, _, setter = self._run()
		self.assertEqual(
			[call.args[0] for call in meta.get_field.call_args_list],
			["transit_pass_no", "lot_no", "party_name", "truck_no_in_tp", "actual_truck_no", "net_weight",
				"quality_test", "tp_status", "date", "quality_check"],
		)
		self.assertEqual([call.args[2] for call in setter.call_args_list], ["1"] * 9 + ["0"])

	def test_touches_no_weighment_records(self):
		db, _, get_doc, _ = self._run(exists=False)
		get_doc.assert_called_once()
		db.set_value.assert_not_called()
		db.sql.assert_not_called()


class TestFinalColumnsPatch(unittest.TestCase):
	def _run(self, exists=True):
		db = MagicMock()
		db.exists.return_value = exists
		meta = MagicMock()
		get_doc = MagicMock()
		with patch.object(frappe, "db", db, create=True), patch.object(
			frappe, "reload_doc", MagicMock(), create=True
		), patch.object(frappe, "get_meta", return_value=meta, create=True), patch.object(
			frappe, "get_doc", get_doc, create=True
		), patch.object(frappe, "clear_cache", MagicMock(), create=True), patch.object(
			final_patch, "set_in_list_view_property"
		) as setter:
			final_patch.execute()
		return db, meta, get_doc, setter

	def test_saves_the_agreed_order_exactly(self):
		db, _, _, _ = self._run()
		saved = json.loads(db.set_value.call_args.args[3])
		self.assertEqual(
			[field["fieldname"] for field in saved],
			["transit_pass_no", "lot_no", "party_name", "actual_truck_no", "net_weight", "quality_check",
				"tp_status", "date"],
		)
		self.assertEqual({f["fieldname"]: f["label"] for f in saved}["transit_pass_no"], "TP No")

	def test_switches_columns_on_and_the_two_old_ones_off(self):
		_, meta, _, setter = self._run()
		calls = [(call.args[1], call.args[2]) for call in setter.call_args_list]
		fields = [call.args[0] for call in meta.get_field.call_args_list]
		self.assertEqual(
			fields,
			["transit_pass_no", "lot_no", "party_name", "actual_truck_no", "net_weight", "quality_check",
				"tp_status", "date", "quality_test", "truck_no_in_tp"],
		)
		self.assertEqual([value for _, value in calls], ["1"] * 8 + ["0"] * 2)

	def test_creates_the_settings_record_when_missing_and_touches_no_weighments(self):
		db, _, get_doc, _ = self._run(exists=False)
		get_doc.assert_called_once()
		db.set_value.assert_not_called()
		db.sql.assert_not_called()


class TestActualTruckNoColumnPatch(unittest.TestCase):
	CURRENT = [
		{"fieldname": "date", "label": "Date & Time"}, {"fieldname": "transit_pass_no", "label": "TP No"},
		{"fieldname": "lot_no", "label": "Lot No"}, {"fieldname": "net_weight", "label": "Net Weight (QT)"},
		{"fieldname": "party_name", "label": "Party Name"}, {"fieldname": "quality_check", "label": "Quality Check SL NO"},
		{"fieldname": "tp_status", "label": "Status"}, {"fieldname": "quality_test", "label": "Quality Test"},
		{"fieldname": "truck_no_in_tp", "label": "Truck No in TP"},
	]

	def _run(self, exists, saved):
		db = MagicMock()
		db.exists.return_value = exists
		db.get_value.return_value = json.dumps(saved) if saved is not None else None
		meta = MagicMock()
		with patch.object(frappe, "db", db, create=True), patch.object(
			frappe, "reload_doc", MagicMock(), create=True
		), patch.object(frappe, "get_meta", return_value=meta, create=True), patch.object(
			frappe, "clear_cache", MagicMock(), create=True
		), patch.object(truck_patch, "set_in_list_view_property") as setter:
			truck_patch.execute()
		return db, meta, setter

	def test_adds_actual_truck_no_after_truck_no_in_tp_and_keeps_the_rest(self):
		db, meta, setter = self._run(True, self.CURRENT)
		saved = json.loads(db.set_value.call_args.args[3])
		names = [field["fieldname"] for field in saved]
		self.assertEqual(names, [f["fieldname"] for f in self.CURRENT] + ["actual_truck_no"])
		self.assertEqual(names.index("transit_pass_no") + 1, names.index("lot_no"))
		meta.get_field.assert_called_once_with("actual_truck_no")
		setter.assert_called_once_with("Weigh Bridge Measurement", meta.get_field.return_value, "1")

	def test_respects_a_reordered_list_and_does_not_add_twice(self):
		reordered = list(reversed(self.CURRENT))
		db, _, _ = self._run(True, reordered)
		names = [field["fieldname"] for field in json.loads(db.set_value.call_args.args[3])]
		self.assertEqual(names[names.index("truck_no_in_tp") + 1], "actual_truck_no")
		self.assertEqual(names.count("actual_truck_no"), 1)
		again = reordered[:5] + [{"fieldname": "actual_truck_no", "label": "Actual Truck No"}] + reordered[5:]
		db, _, setter = self._run(True, again)
		db.set_value.assert_not_called()
		setter.assert_called_once()

	def test_no_saved_list_settings_means_nothing_to_reorder(self):
		db, _, setter = self._run(False, None)
		db.set_value.assert_not_called()
		setter.assert_called_once()


class TestShowTPNoColumnPatch(unittest.TestCase):
	def test_switches_the_tp_no_column_on_through_the_desk_function_only(self):
		field = MagicMock()
		meta = MagicMock()
		meta.get_field.return_value = field
		with patch.object(frappe, "reload_doc", MagicMock(), create=True), patch.object(
			frappe, "get_meta", return_value=meta, create=True
		), patch.object(frappe, "clear_cache", MagicMock(), create=True), patch.object(
			show_patch, "set_in_list_view_property"
		) as setter:
			show_patch.execute()
		meta.get_field.assert_called_once_with("transit_pass_no")
		setter.assert_called_once_with("Weigh Bridge Measurement", field, "1")


class TestWeighBridgeListViewPatch(unittest.TestCase):
	def setUp(self):
		self.db = MagicMock()
		self.db.exists.return_value = False
		self.db.sql.return_value = []
		self.get_doc = MagicMock()
		for patcher in (
			patch.object(frappe, "db", self.db, create=True),
			patch.object(frappe, "get_doc", self.get_doc, create=True),
			patch.object(frappe, "reload_doc", MagicMock(), create=True),
			patch.object(frappe, "clear_cache", MagicMock(), create=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_creates_the_list_view_settings_in_the_requested_order(self):
		patch_module.execute()
		payload = self.get_doc.call_args.args[0]
		self.assertEqual((payload["doctype"], payload["name"]), ("List View Settings", "Weigh Bridge Measurement"))
		self.assertEqual(
			[(f["fieldname"], f["label"]) for f in json.loads(payload["fields"])],
			[("lot_no", "Lot No"), ("party_name", "Party Name"), ("tp_status", "Status"), ("quality_test", "Quality Test"),
				("net_weight", "Net Weight (QT)"), ("truck_no_in_tp", "Truck No in TP"),
				("quality_check", "Quality Check SL NO"), ("date", "Date & Time")],
		)
		self.get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)

	def test_an_existing_list_view_settings_record_is_left_alone(self):
		self.db.exists.return_value = True
		patch_module.execute()
		self.get_doc.assert_not_called()

	def test_saved_sort_is_reset_but_filters_and_other_keys_are_kept(self):
		saved = {"updated_on": "x", "last_view": "List",
			"List": {"filters": [["Weigh Bridge Measurement", "tp_status", "=", "TP Received"]], "sort_by": "modified", "sort_order": "desc"}}
		self.db.sql.side_effect = lambda query, values=None, **kw: (
			[frappe._dict(user="a@x.com", data=json.dumps(saved))] if query.startswith("select") else None
		)
		patch_module.execute()
		update = [call for call in self.db.sql.call_args_list if call.args[0].startswith("update")]
		self.assertEqual(len(update), 1)
		data = json.loads(update[0].args[1][0])
		self.assertEqual((data["List"]["sort_by"], data["List"]["sort_order"]), ("date", "desc"))
		self.assertEqual(data["List"]["filters"], saved["List"]["filters"])
		self.assertEqual((data["last_view"], data["updated_on"]), ("List", "x"))
		self.assertEqual(update[0].args[1][1:], ("a@x.com", "Weigh Bridge Measurement"))

	def test_unreadable_or_listless_user_settings_are_skipped(self):
		rows = [frappe._dict(user="a", data="{not json"), frappe._dict(user="b", data=json.dumps({"Report": {}}))]
		self.db.sql.side_effect = lambda query, values=None, **kw: rows if query.startswith("select") else None
		patch_module.execute()
		self.assertFalse([call for call in self.db.sql.call_args_list if call.args[0].startswith("update")])
