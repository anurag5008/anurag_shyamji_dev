# Copyright (c) 2026, Profezzo and contributors
"""Rice Bran is bought on a quoted Rate Per MT; the Oil Percentage benchmark goes on the Purchase Order and the Actual Oil Percentage
Received on the Purchase Receipt, which then works out the oil-adjusted rate and the amount."""

import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from ivri_od.procurement import purchase_order_mill as po
from ivri_od.procurement import purchase_receipt_mill as pr

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "hooks.py"


class FakeDoc(dict):
	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value

	def set(self, key, value):
		self[key] = value

	def precision(self, fieldname):
		return None


def bran_row(**values):
	base = dict(item_code="RICE-BRAN", quality="Boiled", uom="Quintal", qty=100, idx=1, rate_per_mt=48000, oil_percentage=0, actual_oil_percentage=0, rate=0, avg_wt=0)
	base.update(values)
	return FakeDoc(base)


def doc(doctype, *rows):
	return FakeDoc(doctype=doctype, items=list(rows))


class TestTheClientsFormula(unittest.TestCase):
	def test_the_two_examples_from_the_clients_notes(self):
		self.assertAlmostEqual(po.oil_adjusted_rate(48000, 25, 21.5), 41280, places=6)  # Boiled / Muri Bran
		self.assertAlmostEqual(po.oil_adjusted_rate(46000, 22, 16.5), 34500, places=6)  # Raw Bran

	def test_the_adjusted_rate_is_the_quoted_rate_times_actual_over_benchmark(self):
		self.assertAlmostEqual(po.oil_adjusted_rate(48000, 25, 21.5), 48000 * 21.5 / 25)
		self.assertEqual(po.oil_adjusted_rate(48000, 0, 21.5), 0)  # no benchmark: nothing to adjust


class TestPurchaseOrderRow(unittest.TestCase):
	def test_the_rate_per_quintal_is_the_rate_per_mt_over_ten_and_the_quote_stays(self):
		d = doc("Purchase Order", bran_row())
		po.apply_bran_rate(d)
		row = d["items"][0]
		self.assertEqual((row.rate, row.rate_per_mt), (4800, 48000))

	def test_the_benchmark_starts_at_25_for_boiled_and_muri_and_22_for_raw_and_can_be_kept_if_typed(self):
		for quality, expected in (("Boiled", 25), ("Muri", 25), ("Raw", 22), ("Silky", 0)):
			d = doc("Purchase Order", bran_row(quality=quality))
			po.apply_bran_rate(d)
			self.assertEqual(d["items"][0].oil_percentage, expected, quality)
		d = doc("Purchase Order", bran_row(quality="Boiled", oil_percentage=24))
		po.apply_bran_rate(d)
		self.assertEqual(d["items"][0].oil_percentage, 24)

	def test_a_trip_row_works_too(self):
		d = doc("Purchase Order", bran_row(uom="Trip", avg_wt=25))
		po.apply_bran_rate(d)
		self.assertEqual(d["items"][0].rate, 4800)

	def test_missing_rate_per_mt_a_bag_uom_or_a_wrong_percentage_is_refused(self):
		for name, row in {"no rate": bran_row(rate_per_mt=0), "bags": bran_row(uom="Bags"), "over 100": bran_row(oil_percentage=120)}.items():
			with self.assertRaises(frappe.ValidationError, msg=name):
				po.apply_bran_rate(doc("Purchase Order", row))

	def test_another_item_keeps_none_of_the_bran_fields(self):
		other = bran_row(item_code="PADDY", quality="", rate=2300, oil_percentage=25, rate_per_mt=1)
		po.apply_bran_rate(doc("Purchase Order", other))
		self.assertEqual((other.rate, other.rate_per_mt, other.oil_percentage), (2300, 0, 0))


class TestPurchaseReceiptRow(unittest.TestCase):
	def _receipt(self, row):
		d = doc("Purchase Receipt", row)
		po.apply_bran_rate(d)
		return d, d["items"][0]

	def test_the_boiled_bran_example(self):
		d, row = self._receipt(bran_row(oil_percentage=25, actual_oil_percentage=21.5, qty=300))  # 300 quintal = 30 MT
		self.assertAlmostEqual(row.oil_rate_per_mt, 41280)
		self.assertAlmostEqual(row.rate, 4128)  # per quintal
		self.assertEqual(row.rate_per_mt, 48000)  # the quote is untouched
		self.assertEqual(po.bran_amount(row), 30 * 41280)  # 12,38,400
		self.assertTrue(po.bran_oil_row(d, row))

	def test_the_raw_bran_example(self):
		d, row = self._receipt(bran_row(quality="Raw", rate_per_mt=46000, oil_percentage=22, actual_oil_percentage=16.5, qty=200))  # 20 MT
		self.assertAlmostEqual(row.oil_rate_per_mt, 34500)
		self.assertEqual(po.bran_amount(row), 20 * 34500)  # 6,90,000

	def test_a_trip_is_paid_on_quantity_times_avg_wt_in_mt(self):
		d, row = self._receipt(bran_row(uom="Trip", qty=2, avg_wt=25, oil_percentage=25, actual_oil_percentage=21.5))
		self.assertEqual(po.bran_amount(row), 2 * 25 * 41280)

	def test_without_an_actual_oil_percentage_the_quoted_rate_is_used(self):
		d, row = self._receipt(bran_row(oil_percentage=25))
		self.assertEqual((row.rate, row.oil_rate_per_mt), (4800, 0))
		self.assertFalse(po.bran_oil_row(d, row))

	def test_a_purchase_order_row_is_never_paid_on_oil(self):
		d = doc("Purchase Order", bran_row(oil_percentage=25, actual_oil_percentage=21.5))
		self.assertFalse(po.bran_oil_row(d, d["items"][0]))

	def test_a_higher_actual_oil_than_the_benchmark_is_warned_about_and_not_blocked(self):
		with patch.object(frappe, "msgprint") as warn:
			d, row = self._receipt(bran_row(oil_percentage=25, actual_oil_percentage=27))
		self.assertTrue(warn.called)
		self.assertAlmostEqual(row.oil_rate_per_mt, 51840)

	def test_the_actual_oil_is_needed_to_submit(self):
		with self.assertRaises(frappe.ValidationError):
			pr.require_actual_oil_on_submit(doc("Purchase Receipt", bran_row(qty=10, oil_percentage=25)))
		pr.require_actual_oil_on_submit(doc("Purchase Receipt", bran_row(qty=10, oil_percentage=25, actual_oil_percentage=21)))
		pr.require_actual_oil_on_submit(doc("Purchase Receipt", bran_row(item_code="PADDY", qty=10)))


class TestFixturesHooksPrintAndScripts(unittest.TestCase):
	def test_the_fields_exist_with_the_right_rules(self):
		fields = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text())}
		bran = "eval:doc.item_code=='RICE-BRAN'"
		order_rate = fields["Purchase Order Item-rate_per_mt"]
		self.assertEqual((order_rate["fieldtype"], order_rate["insert_after"], order_rate["depends_on"], order_rate["mandatory_depends_on"]), ("Currency", "rate", bran, bran))
		self.assertEqual(fields["Purchase Order Item-oil_percentage"]["insert_after"], "rate_per_mt")
		for name in ("rate_per_mt", "oil_percentage", "actual_oil_percentage", "oil_rate_per_mt"):
			self.assertEqual(fields[f"Purchase Receipt Item-{name}"]["depends_on"], bran, name)
		self.assertTrue(fields["Purchase Receipt Item-oil_rate_per_mt"]["read_only"])
		hooks = HOOKS.read_text()
		for name in ("Purchase Order Item-rate_per_mt", "Purchase Order Item-oil_percentage", "Purchase Receipt Item-rate_per_mt", "Purchase Receipt Item-oil_percentage", "Purchase Receipt Item-actual_oil_percentage", "Purchase Receipt Item-oil_rate_per_mt"):
			self.assertIn(f'"{name}"', hooks, name)

	def test_the_rule_runs_before_the_totals_on_both_documents_and_is_checked_on_submit(self):
		hooks = HOOKS.read_text()
		self.assertEqual(hooks.count("purchase_order_mill.apply_bran_rate"), 3)  # the order, the receipt and the invoice
		self.assertIn("purchase_receipt_mill.require_actual_oil_on_submit", hooks)

	def test_the_prints_show_the_bran_columns(self):
		formats = {d["name"]: d["html"] for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}
		self.assertIn("Rate / MT", formats["Purchase Order - Shyamji"])
		for text in ("Rate / MT", "Actual Oil %", "Adjusted Rate / MT"):
			self.assertIn(text, formats["Purchase Receipt - Shyamji"])

	def test_the_scripts_follow_the_same_rules(self):
		for name in ("purchase_order_mill.js", "purchase_receipt_mill.js"):
			script = (ROOT / "public" / "js" / name).read_text()
			for part in ("BRAN_OIL_DEFAULT = { Boiled: 25, Muri: 25, Raw: 22 }", "set_bran_defaults", "set_bran_rate", "rate_per_mt(frm, cdt, cdn)"):
				self.assertIn(part, script, f"{name}: {part}")
		self.assertIn("actual_oil_percentage(frm, cdt, cdn)", (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text())


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class TestBranScript(unittest.TestCase):
	HARNESS = r"""
const fs = require("fs");
const out = {};
for (const file of process.argv.slice(1)) {
	let hi = null;
	const locals = {};
	global.locals = locals;
	global.flt = (v) => parseFloat(v) || 0;
	global.precision = () => 4;
	const frappe = {
		ui: { form: { on(dt, h) { if (dt.endsWith("Item")) hi = Object.assign(hi || {}, h); } } },
		form: { link_formatters: {} }, meta: {}, model: { set_value(cdt, cdn, f, v) { locals[cdt][cdn][f] = v; } },
	};
	new Function("frappe", "flt", "locals", fs.readFileSync(file, "utf8"))(frappe, global.flt, locals);
	const cdt = file.includes("receipt") ? "Purchase Receipt Item" : "Purchase Order Item";
	const row = { doctype: cdt, name: "r1", item_code: "RICE-BRAN", quality: "Boiled", uom: "Quintal", qty: 100, rate_per_mt: 0, oil_percentage: 0 };
	locals[cdt] = { r1: row };
	const frm = { doc: { items: [row] }, fields_dict: {}, set_value() {}, toggle_display() {}, cscript: {} };
	const r = {};
	hi.quality(frm, cdt, "r1"); r.boiled = row.oil_percentage;
	row.quality = "Raw"; hi.quality(frm, cdt, "r1"); r.raw = row.oil_percentage;
	row.quality = "Muri"; hi.quality(frm, cdt, "r1"); r.muri = row.oil_percentage;
	row.quality = "Silky"; hi.quality(frm, cdt, "r1"); r.silky = row.oil_percentage;
	row.quality = "Boiled"; hi.quality(frm, cdt, "r1"); row.oil_percentage = 24; row.quality = "Raw"; hi.quality(frm, cdt, "r1"); r.typed_kept = row.oil_percentage;
	row.rate_per_mt = 48000; hi.rate_per_mt(frm, cdt, "r1"); r.rate = row.rate;
	row.uom = "Bags"; row.rate = 0; hi.uom(frm, cdt, "r1"); r.bags_rate = row.rate;
	out[file.split("/").pop()] = r;
}
console.log(JSON.stringify(out));
"""

	def test_the_defaults_and_the_rate_follow_the_quality_and_the_rate_per_mt(self):
		files = [str(ROOT / "public" / "js" / n) for n in ("purchase_order_mill.js", "purchase_receipt_mill.js")]
		result = json.loads(subprocess.run([shutil.which("node"), "-e", self.HARNESS, *files], capture_output=True, text=True, check=True).stdout)
		for name, r in result.items():
			self.assertEqual((r["boiled"], r["raw"], r["muri"], r["silky"]), (25, 22, 25, 0), name)
			self.assertEqual(r["typed_kept"], 24, name)  # a typed percentage is not replaced
			self.assertEqual(r["rate"], 4800, name)
			self.assertEqual(r["bags_rate"], 0, name)  # a Bags row is not given a rate from the MT rate


class TestRateIsHiddenForRiceBran(unittest.TestCase):
	def test_the_rate_is_hidden_and_not_required_on_a_bran_row_of_both_documents(self):
		setters = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		hooks = HOOKS.read_text()
		for doctype in ("Purchase Order Item", "Purchase Receipt Item"):
			hide = setters[f"{doctype}-rate-depends_on"]
			self.assertEqual((hide["field_name"], hide["property"], hide["value"]), ("rate", "depends_on", "eval:doc.item_code!='RICE-BRAN'"))
			self.assertIn("RICE-BRAN", setters[f"{doctype}-rate-mandatory_depends_on"]["value"])
			self.assertIn("PDS", setters[f"{doctype}-rate-mandatory_depends_on"]["value"])  # the PDS exception is kept
		self.assertIn('"Purchase Order Item-rate-depends_on"', hooks)
		self.assertIn('("Purchase Receipt Item", "rate", "depends_on")', hooks)

	def test_the_rate_column_goes_only_when_every_row_is_bran(self):
		for name in ("purchase_order_mill.js", "purchase_receipt_mill.js"):
			script = (ROOT / "public" / "js" / name).read_text()
			self.assertIn("rows_with_item.every(is_bran)", script, name)
			self.assertIn('wanted.push("rate")', script, name)
			self.assertIn('"avg_wt", ...BRAN_COLUMNS, "rate"]', script, name)


@unittest.skipUnless(shutil.which("node"), "Node is not installed")
class TestRateColumnScript(unittest.TestCase):
	HARNESS = r"""
const fs = require("fs");
global.flt = (v) => parseFloat(v) || 0;
global.precision = () => 2;
const out = {};
for (const file of process.argv.slice(1)) {
	let h = null;
	const frappe = {
		ui: { form: { on(dt, handlers) { if (!dt.endsWith("Item")) h = Object.assign(h || {}, handlers); } } },
		form: { link_formatters: {} }, meta: { get_docfield: () => ({ options: "" }) }, model: { set_value() {} },
	};
	global.locals = {};
	new Function("frappe", "flt", "locals", fs.readFileSync(file, "utf8"))(frappe, global.flt, global.locals);
	const shown = {};
	const grid = { grid_rows_by_docname: {}, set_column_disp_in_list_view(fields, show) { fields.forEach((f) => (shown[f] = show)); } };
	const make = (rows) => ({ doc: { items: rows }, fields_dict: { items: { grid } }, set_query() {}, set_value() {}, toggle_display() {}, is_new() { return true; }, cscript: {} });
	const r = {};
	const bran = { doctype: "x", name: "a", item_code: "RICE-BRAN" }, other = { doctype: "x", name: "b", item_code: "PADDY" };
	h.refresh(make([bran])); r.only_bran = shown.rate;
	h.refresh(make([bran, other])); r.mixed = shown.rate;
	h.refresh(make([])); r.empty = shown.rate;
	out[file.split("/").pop()] = r;
}
console.log(JSON.stringify(out));
"""

	def test_the_rate_column_is_hidden_for_bran_only_and_shown_otherwise(self):
		files = [str(ROOT / "public" / "js" / n) for n in ("purchase_order_mill.js", "purchase_receipt_mill.js")]
		result = json.loads(subprocess.run([shutil.which("node"), "-e", self.HARNESS, *files], capture_output=True, text=True, check=True).stdout)
		for name, r in result.items():
			self.assertEqual((r["only_bran"], r["mixed"], r["empty"]), (False, True, True), name)


class TestOilPercentageShowsThePercentSign(unittest.TestCase):
	def test_the_oil_fields_are_percent_fields(self):
		fields = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text())}
		for name in ("Purchase Order Item-oil_percentage", "Purchase Receipt Item-oil_percentage", "Purchase Receipt Item-actual_oil_percentage"):
			self.assertEqual(fields[name]["fieldtype"], "Percent", name)
			self.assertEqual(fields[name]["precision"], "2", name)

	def test_the_prints_write_the_percent_sign_after_the_value(self):
		formats = {d["name"]: d["html"] for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}
		self.assertIn("{{ num(row.oil_percentage, 2) }} %", formats["Purchase Order - Shyamji"])
		for part in ("{{ num(row.oil_percentage, 2) }} %", "{{ num(row.actual_oil_percentage, 2) }} %"):
			self.assertIn(part, formats["Purchase Receipt - Shyamji"])


class TestItemsTableIsNotCut(unittest.TestCase):
	def test_both_scripts_let_headings_and_cells_wrap(self):
		for name in ("purchase_order_mill.js", "purchase_receipt_mill.js"):
			script = (ROOT / "public" / "js" / name).read_text()
			for part in ('[data-fieldname="items"] .grid-heading-row .static-area.ellipsis', '.static-area.ellipsis,', "white-space: normal !important", "text-overflow: clip !important", "word-break: break-word"):
				self.assertIn(part, script, f"{name}: {part}")
			self.assertEqual(script.count("text-overflow: ellipsis"), 0, name)

	def test_the_long_headings_were_shortened_so_they_fit_their_columns(self):
		fields = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text())}
		self.assertEqual(fields["Purchase Receipt Item-actual_oil_percentage"]["label"], "Actual Oil %")
		self.assertEqual(fields["Purchase Receipt Item-oil_percentage"]["label"], "Oil % (Benchmark)")
		self.assertEqual(fields["Purchase Order Item-oil_percentage"]["label"], "Oil %")
		self.assertEqual(fields["Purchase Receipt Item-actual_oil_percentage"]["description"], "Actual Oil Percentage Received (from the test)")
		setters = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		self.assertEqual(setters["Purchase Receipt Item-qty-label"]["value"], "Received Qty")
