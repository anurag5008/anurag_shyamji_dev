# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Warehouse Wise Stock Balance: the Company filter lists only the legal Companies.

A legal Company is the accounting_company of a Mill Master (plus the three approved ones), never recognised by name.
Mocked tests: no site, no database.
"""

import glob
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement import legal_companies as lc
from ivri_od.procurement.inventory_foundation import LEGAL_COMPANIES

SSPP, RGFP, LGI = (LEGAL_COMPANIES[k] for k in ("SSPP", "RGFP", "LGI"))
UNIT_COMPANIES = [
	"Shree Shyamji Paddy Processing Pvt Ltd (Raw)", "Shree Shyamji Paddy Processing Pvt Ltd (Boiled)",
	"Radhe Govind Food Products (Raw)", "Radhe Govind Food Products (Boiled)", "Laddu Gopal Industries (Boiled)",
]
JS = Path(__file__).resolve().parents[2] / "public" / "js" / "warehouse_wise_stock_balance.js"
HOOKS = Path(__file__).resolve().parents[2] / "hooks.py"


class TestLegalCompanyNames(unittest.TestCase):
	def names(self, mapped):
		with patch.object(frappe, "get_all", MagicMock(return_value=mapped), create=True):
			return lc.legal_company_names()

	def test_the_three_approved_legal_companies_are_listed(self):
		self.assertEqual(self.names([]), sorted([SSPP, RGFP, LGI]))
		self.assertEqual({SSPP, RGFP, LGI}, {"Shree Shyamji Paddy Processing Pvt Ltd", "Radhe Govind Food Products", "Laddu Gopal Industries"})

	def test_companies_the_mills_account_to_are_included_once(self):
		mapped = [SSPP, SSPP, RGFP, LGI]  # five mills, three Companies
		self.assertEqual(self.names(mapped), sorted([SSPP, RGFP, LGI]))

	def test_a_new_legal_company_only_needs_its_mills_mapped_to_it(self):
		self.assertEqual(self.names([SSPP, "Another Legal Company"]), sorted([SSPP, RGFP, LGI, "Another Legal Company"]))

	def test_blank_mappings_are_ignored(self):
		self.assertEqual(self.names(["", None, "  "]), sorted([SSPP, RGFP, LGI]))

	def test_the_five_operating_unit_companies_are_never_listed(self):
		names = self.names([SSPP, RGFP, LGI])
		for unit_company in UNIT_COMPANIES:
			self.assertNotIn(unit_company, names)

	def test_the_rule_reads_the_accounting_company_field_not_names(self):
		with patch.object(frappe, "get_all", MagicMock(return_value=[]), create=True) as get_all:
			lc.legal_company_names()
		self.assertEqual(get_all.call_args.args[0], "Mill Master")
		self.assertEqual(get_all.call_args.kwargs["pluck"], "accounting_company")
		source = Path(lc.__file__).read_text()
		code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith(("#", '"""')))
		for fragile in ("(Raw)", "(Boiled)", "Raw)", "Boiled)", "endswith", "startswith", ".split("):
			self.assertNotIn(fragile, code)


def search(*args):
	"""legal_company_query without the search-input sanitiser, which needs a bound site."""
	import inspect

	return inspect.unwrap(lc.legal_company_query)(*args)


class TestQueries(unittest.TestCase):
	def setUp(self):
		self.get_list = MagicMock(return_value=[LGI, RGFP, SSPP])
		for target, value in (("get_list", self.get_list), ("get_all", MagicMock(return_value=[SSPP, RGFP, LGI]))):
			patcher = patch.object(frappe, target, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)

	def test_the_dropdown_returns_the_legal_companies_in_the_link_search_shape(self):
		rows = search("Company", "", "name", 0, 20, {})
		self.assertEqual(rows, [[LGI], [RGFP], [SSPP]])

	def test_the_search_is_limited_to_the_legal_names_and_the_typed_text(self):
		search("Company", "Radhe", "name", 0, 20, {})
		filters = self.get_list.call_args.kwargs["filters"]
		self.assertEqual(filters[0][:2], ["name", "in"])
		self.assertEqual(sorted(filters[0][2]), sorted([SSPP, RGFP, LGI]))
		self.assertEqual(filters[1], ["name", "like", "%Radhe%"])

	def test_paging_arguments_are_passed_on(self):
		search("Company", "", "name", 10, 5, {})
		self.assertEqual((self.get_list.call_args.kwargs["limit_start"], self.get_list.call_args.kwargs["limit_page_length"]), (10, 5))

	def test_the_list_for_the_form_uses_the_same_rule_and_the_users_permissions(self):
		self.assertEqual(lc.get_legal_companies(), [LGI, RGFP, SSPP])
		self.assertEqual(self.get_list.call_args.args[0], "Company")  # get_list, not get_all: permissions apply

	def test_both_entry_points_can_be_called_from_the_browser(self):
		self.assertIn(lc.get_legal_companies, frappe.whitelisted)
		self.assertIn(lc.legal_company_query, frappe.whitelisted)


def _node():
	found = shutil.which("node")
	if found:
		return found
	matches = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
	return matches[-1] if matches else None


HARNESS = r"""
const fs = require("fs");
const file = process.argv.slice(-1)[0];
const calls = [];
const LEGAL = ["Laddu Gopal Industries", "Radhe Govind Food Products", "Shree Shyamji Paddy Processing Pvt Ltd"];
const frappe = {
	provide(path) { path.split(".").slice(1).reduce((o, k) => (o[k] = o[k] || {}), frappe); },
	xcall(method) { calls.push(method); return Promise.resolve(LEGAL); },
};
frappe.provide("frappe.query_reports");
const styles = [];
const document = {
	head: { appendChild(el) { styles.push(el); } },
	getElementById(id) { return styles.find((el) => el.id === id) || null; },
	createElement() { return {}; },
};
new Function("frappe", "document", fs.readFileSync(file, "utf8"))(frappe, document);
const R = "Warehouse Wise Stock Balance";
const erpnext = () => ({
	filters: [
		{ fieldname: "company", label: "Company", fieldtype: "Link", options: "Company", reqd: 1 },
		{ fieldname: "show_disabled_warehouses", label: "Show Disabled Warehouses", fieldtype: "Check", default: 0 },
	],
	initial_depth: 3, tree: true, parent_field: "parent_warehouse", name_field: "warehouse",
});
const control = (value) => ({ value, classes: [], $wrapper: { addClass(c) { this.owner.classes.push(c); } }, get_value() { return this.value; }, set_value(v) { this.value = v; } });
let last;
const run = async (value, extra) => {
	const c = control(value);
	c.$wrapper.owner = c;
	last = c;
	const settings = frappe.query_reports[R];
	const report = { get_filter: (name) => (name === "company" ? c : undefined) };
	await settings.onload(report);
	return c.value;
};
(async () => {
	const out = {};
	out.empty_before_the_script = frappe.query_reports[R] === undefined;  // Frappe loads the script only while this is empty
	frappe.query_reports[R] = erpnext();  // what ERPNext's own report script does
	const s = frappe.query_reports[R];
	const company = s.filters.find((f) => f.fieldname === "company");
	const other = s.filters.find((f) => f.fieldname === "show_disabled_warehouses");
	out.query = company.get_query();
	out.company_filter = { fieldtype: company.fieldtype, options: company.options, reqd: company.reqd, label: company.label };
	out.other_filter_untouched = !("get_query" in other) && other.fieldtype === "Check" && other.default === 0;
	out.settings_untouched = s.initial_depth === 3 && s.tree === true && s.parent_field === "parent_warehouse" && s.name_field === "warehouse";
	const onload_once = s.onload;
	frappe.query_reports[R] = s;  // Frappe assigns the same settings again after loading
	out.idempotent = frappe.query_reports[R].onload === onload_once;
	frappe.query_reports["Stock Balance"] = erpnext();  // another stock report: must stay as it is
	out.other_report_untouched = !("get_query" in frappe.query_reports["Stock Balance"].filters[0]) && !frappe.query_reports["Stock Balance"].onload;
	out.keeps_a_legal_default = await run("Radhe Govind Food Products");
	out.clears_an_operating_unit_company = await run("Shree Shyamji Paddy Processing Pvt Ltd (Raw)");
	out.leaves_an_empty_filter_alone = await run("");
	const asked_before = calls.length;
	await run("");
	out.no_server_call_for_an_empty_filter = calls.length === asked_before;
	out.server_method = calls[0];
	// an existing onload is kept and runs first
	const order = [];
	const R2 = "Warehouse Wise Stock Balance";
	delete frappe.query_reports[R2];
	frappe.query_reports[R2] = Object.assign(erpnext(), { onload() { order.push("original"); } });
	await frappe.query_reports[R2].onload({ get_filter: () => undefined });
	out.original_onload_runs = order;
	out.width_class_on_company_only = last.classes.includes("ivri-wide-company-filter") && last.classes.length === 1;
	out.style_added_once = styles.length === 1 && styles[0].id === "ivri-wide-company-filter-style";
	out.style_rule = styles[0].textContent;
	console.log(JSON.stringify(out));
})();
"""


@unittest.skipUnless(_node(), "Node is not installed")
class TestTheReportScript(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		out = subprocess.run([_node(), "-e", HARNESS, str(JS)], capture_output=True, text=True, check=True)
		cls.result = json.loads(out.stdout)

	def test_the_report_is_loaded_normally_because_the_key_is_empty_until_erpnexts_script_sets_it(self):
		self.assertTrue(self.result["empty_before_the_script"])

	def test_the_company_filter_asks_the_legal_company_query(self):
		self.assertEqual(self.result["query"], {"query": "ivri_od.procurement.legal_companies.legal_company_query"})

	def test_the_company_filter_is_otherwise_unchanged(self):
		self.assertEqual(self.result["company_filter"], {"fieldtype": "Link", "options": "Company", "reqd": 1, "label": "Company"})

	def test_nothing_else_of_the_report_is_changed(self):
		self.assertTrue(self.result["other_filter_untouched"])
		self.assertTrue(self.result["settings_untouched"])

	def test_it_is_applied_once_even_if_frappe_assigns_the_settings_again(self):
		self.assertTrue(self.result["idempotent"])

	def test_other_stock_reports_are_not_touched(self):
		self.assertTrue(self.result["other_report_untouched"])

	def test_a_legal_default_stays_and_an_operating_unit_company_is_cleared(self):
		self.assertEqual(self.result["keeps_a_legal_default"], "Radhe Govind Food Products")
		self.assertEqual(self.result["clears_an_operating_unit_company"], "")
		self.assertEqual(self.result["leaves_an_empty_filter_alone"], "")

	def test_an_empty_filter_asks_the_server_nothing(self):
		self.assertTrue(self.result["no_server_call_for_an_empty_filter"])
		self.assertEqual(self.result["server_method"], "ivri_od.procurement.legal_companies.get_legal_companies")

	def test_an_onload_the_report_already_had_still_runs(self):
		self.assertEqual(self.result["original_onload_runs"], ["original"])


@unittest.skipUnless(_node(), "Node is not installed")
class TestWidth(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		out = subprocess.run([_node(), "-e", HARNESS, str(JS)], capture_output=True, text=True, check=True)
		cls.result = json.loads(out.stdout)

	def test_the_company_filter_gets_the_width_class_and_the_style_is_added_once(self):
		self.assertTrue(self.result["width_class_on_company_only"])
		self.assertTrue(self.result["style_added_once"])

	def test_the_width_is_responsive_and_limited_to_the_company_filter(self):
		rule = self.result["style_rule"]
		self.assertIn("clamp(360px, 40vw, 480px)", rule)
		self.assertIn("max-width: 100%", rule)
		self.assertIn(".page-form .frappe-control.ivri-wide-company-filter", rule)
		self.assertNotIn("data-fieldname", rule)  # no other filter is touched


class TestWiring(unittest.TestCase):
	def test_the_script_is_loaded_on_the_desk(self):
		self.assertIn('"/assets/ivri_od/js/warehouse_wise_stock_balance.js?v=2"', HOOKS.read_text())

	def test_the_script_names_no_company_and_no_name_pattern(self):
		source = JS.read_text()
		for fragment in ("Shyamji", "Radhe", "Laddu", "(Raw)", "(Boiled)", "Raw", "Boiled"):
			self.assertNotIn(fragment, source)

	def test_erpnext_itself_is_not_modified(self):
		erpnext_js = Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "stock" / "report" / "warehouse_wise_stock_balance" / "warehouse_wise_stock_balance.js"
		self.assertNotIn("get_query", erpnext_js.read_text())
		self.assertNotIn("legal", erpnext_js.read_text())


if __name__ == "__main__":
	unittest.main()
