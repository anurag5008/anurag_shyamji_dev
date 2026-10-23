# Copyright (c) 2026, Profezzo and contributors

import json
import os
import re
import shutil
import sqlite3
import subprocess
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.patches.v1_0 import rename_rice_dispatch_summary_report as rename_patch
from ivri_od.procurement.report.rice_dispatch import rice_dispatch as report

REPORT_JSON = os.path.join(
	os.path.dirname(__file__), "..", "report", "rice_dispatch", "rice_dispatch.json"
)


class _SqliteDb:
	"""Runs the report's own SQL on an in-memory database, so totals and date filters are really executed."""

	def __init__(self):
		self.conn = sqlite3.connect(":memory:")
		self.conn.row_factory = sqlite3.Row
		self.conn.executescript(
			"""
			create table `tabWeigh Bridge Measurement` (
				name text, party_name text, date text, net_weight real, tp_status text, docstatus integer);
			create table `tabDepo Master` (name text, depo_name text, creation text);
			"""
		)

	def add_wbm(self, name, party, when, net, status="Rice Dispatch", docstatus=0):
		self.conn.execute(
			"insert into `tabWeigh Bridge Measurement` values (?, ?, ?, ?, ?, ?)",
			(name, party, when, net, status, docstatus),
		)

	def add_depo(self, code, depo_name, creation="2026-01-01 00:00:00"):
		self.conn.execute("insert into `tabDepo Master` values (?, ?, ?)", (code, depo_name, creation))

	def sql(self, query, values=None, as_dict=False):
		query = re.sub(r"%\((\w+)\)s", r":\1", query)
		params = {
			key: value.isoformat() if isinstance(value, (date, datetime)) else value
			for key, value in (values or {}).items()
		}
		rows = [frappe._dict(row) for row in self.conn.execute(query, params).fetchall()]
		for row in rows:
			if row.get("date"):
				row["date"] = datetime.fromisoformat(row["date"])
		return rows

	def exists(self, doctype, name=None):
		if doctype != "Depo Master":
			return False
		return bool(self.conn.execute("select 1 from `tabDepo Master` where name = ?", (name,)).fetchone())

	def get_value(self, doctype, name, fieldname):
		row = self.conn.execute(f"select `{fieldname}` from `tabDepo Master` where name = ?", (name,)).fetchone()
		return row[0] if row else None


class TestRiceDispatchSummary(unittest.TestCase):
	def setUp(self):
		self.db = _SqliteDb()
		frappe.local.lang = "en"
		for patcher in (
			patch.object(frappe, "db", self.db, create=True),
			# flt(x, precision) reads the rounding method; there is no site here
			patch.object(frappe, "get_system_settings", lambda *args, **kwargs: None, create=True),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.db.add_depo("DW051105", "Malmunda")
		self.db.add_depo("DW051301", "CHARBHATA")
		self.db.add_depo("DG051601", "RMC,Kantabanji")
		# Malmunda: three dispatches, the party typed in different case / spacing
		self.db.add_wbm("W1", "MALMUNDA", "2026-10-05 09:00:00", 100.5)
		self.db.add_wbm("W2", "  malmunda ", "2026-10-20 18:30:00", 50.25)
		self.db.add_wbm("W3", "Malmunda", "2026-10-12 11:00:00", 200.0)
		# Charbhata: one dispatch; RMC: two
		self.db.add_wbm("W4", "CHARBHATA", "2026-10-12 08:00:00", 75.0)
		self.db.add_wbm("W5", "RMC,Kantabanji", "2026-09-30 23:59:59", 10.0)
		self.db.add_wbm("W6", "RMC,Kantabanji", "2026-10-01 00:00:00", 20.0)
		# not Rice Dispatch, cancelled, and a Rice Dispatch weighment rejected at QC (net weight 0)
		self.db.add_wbm("X1", "MALMUNDA", "2026-10-06 10:00:00", 999.0, status="TP Received")
		self.db.add_wbm("X2", "MALMUNDA", "2026-10-06 10:00:00", 888.0, docstatus=2)
		self.db.add_wbm("W7", "CHARBHATA", "2026-10-13 10:00:00", 0.0)

	def _rows(self, **filters):
		return {row["depot_name"]: row for row in report.get_data(filters)}

	def test_depot_wise_totals_and_counts(self):
		rows = self._rows()
		self.assertEqual(sorted(rows), ["CHARBHATA", "Malmunda", "RMC,Kantabanji"])
		malmunda = rows["Malmunda"]
		self.assertEqual((malmunda["dispatches"], malmunda["total_qt"]), (3, 350.75))
		charbhata = rows["CHARBHATA"]
		self.assertEqual((charbhata["dispatches"], charbhata["total_qt"]), (2, 75.0))
		rmc = rows["RMC,Kantabanji"]
		self.assertEqual((rmc["dispatches"], rmc["total_qt"]), (2, 30.0))

	def test_rows_hold_only_the_three_columns_and_the_depot_code_for_the_link(self):
		for row in report.get_data({}):
			self.assertEqual(set(row), {"depot_name", "depot_code", "dispatches", "total_qt"})
		rows = self._rows()
		self.assertEqual(
			(rows["Malmunda"]["depot_code"], rows["CHARBHATA"]["depot_code"], rows["RMC,Kantabanji"]["depot_code"]),
			("DW051105", "DW051301", "DG051601"),
		)

	def test_other_statuses_and_cancelled_records_are_ignored(self):
		self.assertEqual(sum(row["dispatches"] for row in self._rows().values()), 7)
		self.assertEqual(sum(row["total_qt"] for row in self._rows().values()), 455.75)

	def test_quantities_are_qt_as_stored_with_no_conversion(self):
		self.assertEqual(self._rows()["Malmunda"]["total_qt"], 350.75)  # 100.5 + 50.25 + 200, not divided by 10
		self.assertEqual(self._rows(depot_name="DW051301")["CHARBHATA"]["total_qt"], 75.0)

	def test_from_and_to_dates_are_both_included(self):
		rows = self._rows(from_date="2026-10-05", to_date="2026-10-12")
		self.assertEqual(sorted(rows), ["CHARBHATA", "Malmunda"])
		self.assertEqual((rows["Malmunda"]["dispatches"], rows["Malmunda"]["total_qt"]), (2, 300.5))  # W1 (5th) and W3 (12th)
		self.assertEqual((rows["CHARBHATA"]["dispatches"], rows["CHARBHATA"]["total_qt"]), (1, 75.0))

	def test_a_day_filter_includes_the_whole_day(self):
		rows = self._rows(from_date="2026-10-20", to_date="2026-10-20")  # W2 is at 18:30
		self.assertEqual(list(rows), ["Malmunda"])
		self.assertEqual(rows["Malmunda"]["total_qt"], 50.25)
		rows = self._rows(from_date="2026-09-30", to_date="2026-09-30")  # W5 is at 23:59:59
		self.assertEqual(list(rows), ["RMC,Kantabanji"])

	def test_one_sided_date_filters(self):
		after = self._rows(from_date="2026-10-13")
		self.assertEqual({name: row["dispatches"] for name, row in after.items()}, {"Malmunda": 1, "CHARBHATA": 1})
		before = self._rows(to_date="2026-10-01")
		self.assertEqual({name: row["dispatches"] for name, row in before.items()}, {"RMC,Kantabanji": 2})

	def test_dates_outside_all_dispatches_give_no_rows(self):
		self.assertEqual(report.get_data({"from_date": "2027-01-01"}), [])
		self.assertEqual(report.get_data({"to_date": "2025-01-01"}), [])

	def test_from_date_after_to_date_is_rejected(self):
		with patch.object(frappe, "throw", side_effect=frappe.ValidationError, create=True):
			with self.assertRaises(frappe.ValidationError):
				report.get_data({"from_date": "2026-10-20", "to_date": "2026-10-01"})

	def test_depot_filter_by_depo_master_code_or_by_name_ignoring_case(self):
		for value in ("DW051105", "Malmunda", "MALMUNDA", "  malmunda "):
			rows = self._rows(depot_name=value)
			self.assertEqual(list(rows), ["Malmunda"], value)
			self.assertEqual(rows["Malmunda"]["dispatches"], 3, value)

	def test_depot_filter_with_unknown_depot_gives_no_rows(self):
		self.assertEqual(report.get_data({"depot_name": "No Such Depot"}), [])

	def test_depot_and_date_filters_together(self):
		rows = self._rows(depot_name="DW051105", from_date="2026-10-10", to_date="2026-10-31")
		self.assertEqual(rows["Malmunda"]["dispatches"], 2)
		self.assertEqual(rows["Malmunda"]["total_qt"], 250.25)

	def test_depot_not_in_depo_master_is_still_listed_by_its_party_name(self):
		self.db.add_wbm("Z1", "  Old Depot  ", "2026-10-15 10:00:00", 5.0)
		self.assertIn("Old Depot", self._rows())
		self.assertEqual(self._rows()["Old Depot"]["depot_code"], "")

	def test_depot_name_comes_from_depo_master_spelling(self):
		self.assertIn("Malmunda", self._rows())
		self.assertNotIn("MALMUNDA", self._rows())

	def test_rows_are_sorted_by_depot_name(self):
		names = [row["depot_name"] for row in report.get_data({})]
		self.assertEqual(names, sorted(names, key=str.casefold))

	def test_columns_have_no_mt_column_and_use_qt(self):
		columns = report.get_columns()
		self.assertEqual(
			[(c["fieldname"], c["label"]) for c in columns],
			[
				("depot_name", "Depot Name"),
				("dispatches", "Number of Dispatches"),
				("total_qt", "Total Rice Dispatched (QT)"),
			],
		)
		for column in columns:
			self.assertNotIn("MT", column["label"].upper().split())
			self.assertNotIn("_mt", column["fieldname"])
			self.assertNotIn("Date", column["label"])  # no First / Last Dispatch Date

	def test_no_dispatch_date_column_anywhere_in_the_report(self):
		folder = os.path.dirname(REPORT_JSON)
		for name in ("rice_dispatch.py", "rice_dispatch.js"):
			with open(os.path.join(folder, name)) as handle:
				source = handle.read()
			self.assertNotIn("first_dispatch", source, name)
			self.assertNotIn("last_dispatch", source, name)
			self.assertNotIn("First Dispatch Date", source, name)
			self.assertNotIn("Last Dispatch Date", source, name)

	def test_report_is_a_standard_script_report_with_a_grand_total_row(self):
		with open(REPORT_JSON) as handle:
			meta = json.load(handle)
		self.assertEqual(meta["add_total_row"], 1)
		self.assertEqual((meta["ref_doctype"], meta["report_type"], meta["module"]), ("Weigh Bridge Measurement", "Script Report", "Procurement"))
		self.assertEqual({r["role"] for r in meta["roles"]}, {"System Manager", "Desk User"})

	def test_the_grand_total_adds_dispatches_and_quantity(self):
		from frappe.desk.query_report import add_total_row

		columns, data = report.execute({})
		data = add_total_row(list(data), columns)
		# Frappe's own grand-total row is a list in column order: label, dispatches, quantity
		label, dispatches, total_qt = data[-1]
		self.assertEqual((label, dispatches, round(total_qt, 3)), ("Total", 7, 455.75))
		self.assertEqual(len(data), 4)  # three depots and the total

	def test_filters_are_the_requested_ones(self):
		path = os.path.join(os.path.dirname(REPORT_JSON), "rice_dispatch.js")
		with open(path) as handle:
			source = handle.read()
		for fieldname in ("from_date", "to_date", "depot_name"):
			self.assertIn(f'fieldname: "{fieldname}"', source)
		self.assertIn('options: "Depo Master"', source)


_REPORT_HARNESS = """
const fs = require('fs'), vm = require('vm');
const escape_html = (t) => String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const sandbox = { frappe: { query_reports: {}, utils: { escape_html } }, __: (t) => t,
  flt: (v) => Number(v) || 0, cint: (v) => parseInt(v, 10) || 0, window: {}, document: {} };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
const report = sandbox.frappe.query_reports['Rice Dispatch'];
const plain = (value) => String(value);
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify({
  layout: report.get_datatable_options({}),
  filters: report.filters.map((f) => [f.fieldname, f.fieldtype, f.options || null]),
  cells: cases.map((c) => report.formatter(c.value, [], { fieldname: c.fieldname }, c.data, plain)),
}));
"""

_REPORT_JS = os.path.join(os.path.dirname(REPORT_JSON), "rice_dispatch.js")
_ENTRY_JS = os.path.join(os.path.dirname(REPORT_JSON), "..", "entry_report", "entry_report.js")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class TestRiceDispatchSummaryDesign(unittest.TestCase):
	"""The report is drawn like the Entry Report."""

	def _run(self, cases):
		done = subprocess.run(
			["node", "-e", _REPORT_HARNESS, _REPORT_JS, json.dumps(cases)], capture_output=True, text=True, check=True
		)
		return json.loads(done.stdout)

	def test_same_datatable_layout_as_entry_report(self):
		layout = self._run([])["layout"]
		self.assertEqual((layout["layout"], layout["cellHeight"]), ("fixed", 36))
		with open(_ENTRY_JS) as handle:
			entry = handle.read()
		self.assertIn('layout: "fixed"', entry)
		self.assertIn("cellHeight: 36", entry)

	def test_filters_are_from_date_to_date_and_depot_name(self):
		self.assertEqual(
			self._run([])["filters"],
			[["from_date", "Date", None], ["to_date", "Date", None], ["depot_name", "Link", "Depo Master"]],
		)

	def test_numbers_are_right_aligned_with_fixed_decimals(self):
		cells = self._run([
			{"fieldname": "dispatches", "value": 7},
			{"fieldname": "total_qt", "value": 455.75},
			{"fieldname": "total_qt", "value": 0},
		])["cells"]
		for cell in cells:
			self.assertIn("text-align: right", cell)
			self.assertIn("tabular-nums", cell)
		self.assertIn(">7<", cells[0])
		self.assertIn(">455.750<", cells[1])
		self.assertIn(">0.000<", cells[2])

	def test_depot_name_links_to_its_depo_master_and_total_row_is_plain(self):
		linked, total, no_code, tricky = self._run([
			{"fieldname": "depot_name", "value": "Malmunda", "data": {"depot_code": "DW051105"}},
			{"fieldname": "depot_name", "value": "Total", "data": {}},
			{"fieldname": "depot_name", "value": "Old Depot", "data": {"depot_code": ""}},
			{"fieldname": "depot_name", "value": "<b>x</b>", "data": {"depot_code": "A B"}},
		])["cells"]
		self.assertIn('href="/app/depo-master/DW051105"', linked)
		self.assertIn('data-doctype="Depo Master"', linked)
		self.assertEqual((total, no_code), ("Total", "Old Depot"))
		self.assertIn("/app/depo-master/A%20B", tricky)
		self.assertIn("&lt;b&gt;x&lt;/b&gt;", tricky)
		self.assertNotIn("<b>", tricky)

	def test_total_row_numbers_are_formatted_and_blank_cells_left_alone(self):
		cells = self._run([
			{"fieldname": "total_qt", "value": ""},
			{"fieldname": "dispatches", "value": None},
			{"fieldname": "total_qt", "value": 150},
		])["cells"]
		self.assertEqual(cells[0], "")
		self.assertEqual(cells[1], "null")
		self.assertIn(">150.000<", cells[2])

	def test_section_band_is_drawn_and_does_not_clash_with_entry_report(self):
		with open(_REPORT_JS) as handle:
			source = handle.read()
		self.assertIn("render_rice_dispatch_super_header(datatable_obj)", source)
		self.assertIn('__("Dispatch Summary")', source)
		with open(_ENTRY_JS) as handle:
			entry = handle.read()
		for name in ("function render_rice_dispatch_super_header", "function inject_rice_dispatch_report_styles"):
			self.assertIn(name, source)
			self.assertNotIn(name, entry)
		for name in ("function render_entry_report_super_header", "function inject_entry_report_styles"):
			self.assertNotIn(name, source)
		self.assertIn("rice-dispatch-report-ui-styles", source)
		self.assertNotIn("entry-report-ui-styles", source)


class TestRiceDispatchReportRename(unittest.TestCase):
	def _run(self, exists):
		db = MagicMock()
		db.exists.side_effect = lambda doctype, name=None: exists.get(name, False)
		with patch.object(frappe, "db", db, create=True), patch.object(
			frappe, "reload_doc", MagicMock(), create=True
		) as reload_doc, patch.object(frappe, "clear_cache", MagicMock(), create=True):
			rename_patch.execute()
		return db, reload_doc

	def test_report_json_is_named_rice_dispatch(self):
		with open(REPORT_JSON) as handle:
			meta = json.load(handle)
		self.assertEqual((meta["name"], meta["report_name"]), ("Rice Dispatch", "Rice Dispatch"))
		self.assertEqual(os.path.basename(REPORT_JSON), "rice_dispatch.json")

	def test_script_registers_under_the_new_name_and_no_old_name_is_left(self):
		with open(_REPORT_JS) as handle:
			source = handle.read()
		self.assertIn('frappe.query_reports["Rice Dispatch"]', source)
		root = os.path.join(os.path.dirname(REPORT_JSON), "..", "..", "..")
		for relative in ("procurement/procurement_workspace.py", "workspace_sidebar/procurement.json",
			"procurement/workspace/procurement/procurement.json"):
			with open(os.path.join(root, relative)) as handle:
				text = handle.read()
			self.assertNotIn("Rice Dispatch Summary", text, relative)
			self.assertNotIn("Rice%20Dispatch%20Summary", text, relative)

	def test_old_report_definition_is_dropped_once_the_new_one_exists(self):
		db, reload_doc = self._run({"Rice Dispatch": True, "Rice Dispatch Summary": True})
		reload_doc.assert_called_once_with("procurement", "report", "rice_dispatch")
		self.assertEqual(
			[(call.args[0], call.args[1]) for call in db.delete.call_args_list],
			[("Has Role", {"parent": "Rice Dispatch Summary", "parenttype": "Report"}),
				("Report", {"name": "Rice Dispatch Summary"})],
		)

	def test_old_definition_is_kept_when_the_new_one_is_not_there_yet(self):
		db, _ = self._run({"Rice Dispatch": False, "Rice Dispatch Summary": True})
		db.delete.assert_not_called()

	def test_nothing_to_do_when_the_old_report_is_already_gone(self):
		db, _ = self._run({"Rice Dispatch": True, "Rice Dispatch Summary": False})
		db.delete.assert_not_called()
