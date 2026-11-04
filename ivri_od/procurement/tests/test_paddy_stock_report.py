# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Warehouse Wise Stock Balance: the Stock Balance column becomes Paddy Stock, from GRN Net Weight (QT).

Runs ERPNext's own report functions against the replacements. Mocked tests: no site, no database."""

import importlib
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement import paddy_stock_report as psr

HOOKS = Path(psr.__file__).resolve().parents[1] / "hooks.py"
SSPP = "Shree Shyamji Paddy Processing Pvt Ltd"
RGFP = "Radhe Govind Food Products"


def warehouse(name, parent=None, is_group=0, disabled=0):
	return frappe._dict(name=name, parent_warehouse=parent, is_group=is_group, disabled=disabled)


SSPP_TREE = [
	warehouse("All Warehouses - SSPP", is_group=1),
	warehouse("GODOWN - SSPP", "All Warehouses - SSPP"),
	warehouse("GALI - SSPP", "All Warehouses - SSPP"),
	warehouse("OPEN GODOWN - SSPP", "All Warehouses - SSPP"),
]


class PaddyStockCase(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		# flt(x, 3) reads the rounding method from System Settings; no site is bound, so use the default
		patcher = patch.object(frappe, "get_system_settings", lambda key: None, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)
		psr.uninstall()
		self.addCleanup(psr.uninstall)
		self.module = importlib.import_module(psr.REPORT_MODULE)
		self.original = (self.module.get_warehouse_wise_balance, self.module.get_columns)

	def rows(self, rows):
		query = MagicMock()
		query.run.return_value = rows
		patcher = patch.object(psr, "paddy_stock_query", return_value=query)
		patcher.start()
		self.addCleanup(patcher.stop)
		return query

	def report_data(self, tree=SSPP_TREE, **filters):
		with patch.object(frappe, "get_all", MagicMock(return_value=[frappe._dict(w) for w in tree]), create=True):
			return {w.name: w.stock_balance for w in self.module.get_data(frappe._dict(company=SSPP, **filters))}


class TestTheQuery(PaddyStockCase):
	def sql(self):
		from frappe.query_builder import get_query_builder

		with patch.object(frappe, "qb", get_query_builder("mariadb"), create=True):
			return str(psr.paddy_stock_query())

	def test_it_sums_grn_net_weight_by_the_unloading_point_of_the_grns_quality_check(self):
		sql = self.sql()
		self.assertIn("`tabGRN Note`", sql)
		self.assertIn("JOIN `tabQuality Check`", sql)
		self.assertIn("`tabQualityCheck`.`name`=`tabGRNNote`.`quality_check`", sql.replace(" ", ""))
		self.assertIn("SUM(`tabGRN Note`.`net_weight`)", sql)
		self.assertIn("GROUP BY `tabQuality Check`.`unloading_point`", sql)

	def test_every_grn_counts_whether_or_not_it_is_local_or_accepted_only_cancelled_ones_do_not(self):
		sql = self.sql().replace(" ", "")
		self.assertIn("`tabGRNNote`.`docstatus`<2", sql)
		for not_used in ("is_local_procurement", "qc_decision", "quality_test", "tp_status"):
			self.assertNotIn(not_used, sql)

	def test_a_blank_unloading_point_is_left_out(self):
		sql = self.sql().replace(" ", "")
		self.assertIn("`unloading_point`ISNOTNULL", sql)
		self.assertIn("`unloading_point`<>''", sql)

	def test_the_stock_ledger_is_not_read(self):
		sql = self.sql()
		self.assertNotIn("Stock Ledger Entry", sql)
		self.assertNotIn("stock_value", sql)


class TestTheTotals(PaddyStockCase):
	def test_totals_are_per_warehouse_with_three_decimals(self):
		self.rows([("GODOWN - SSPP", 157.2580000001), ("GALI - SSPP", 78.0)])
		self.assertEqual(psr.get_paddy_stock_by_warehouse({}), {"GODOWN - SSPP": 157.258, "GALI - SSPP": 78.0})

	def test_a_warehouse_listed_twice_is_added_not_overwritten(self):
		self.rows([("GODOWN - SSPP", 86.07), ("GODOWN - SSPP", 71.188)])
		self.assertEqual(psr.get_paddy_stock_by_warehouse({})["GODOWN - SSPP"], 157.258)

	def test_no_grn_rows_gives_nothing(self):
		for empty in ([], None):
			self.rows(empty)
			self.assertEqual(psr.get_paddy_stock_by_warehouse({}), {})

	def test_the_company_filter_is_not_needed_because_the_report_lists_that_companys_warehouses(self):
		self.rows([("GODOWN - SSPP", 10.0)])
		self.assertEqual(psr.get_paddy_stock_by_warehouse({"company": RGFP}), {"GODOWN - SSPP": 10.0})


class TestTheColumn(PaddyStockCase):
	def test_stock_balance_is_renamed_paddy_stock_and_the_rest_is_untouched(self):
		columns = psr.paddy_stock_columns(
			[
				{"label": "Warehouse", "fieldname": "name", "fieldtype": "Link", "options": "Warehouse", "width": 200},
				{"label": "Stock Balance", "fieldname": "stock_balance", "fieldtype": "Float", "width": 150},
				{"label": "Warehouse Disabled?", "fieldname": "disabled", "fieldtype": "Check", "width": 200},
			]
		)
		self.assertEqual([c["label"] for c in columns], ["Warehouse", "Paddy Stock", "Warehouse Disabled?"])
		self.assertEqual(columns[1]["fieldname"], "stock_balance")  # ERPNext's own code still fills it
		self.assertEqual((columns[1]["fieldtype"], columns[1]["precision"]), ("Float", 3))
		self.assertNotIn("precision", columns[0])


class TestInstalledIntoErpnextsReport(PaddyStockCase):
	def setUp(self):
		super().setUp()
		psr.install()

	def test_the_report_columns_say_paddy_stock(self):
		columns = self.module.get_columns(frappe._dict())
		self.assertEqual([c["fieldname"] for c in columns], ["name", "stock_balance"])
		self.assertEqual([c["label"] for c in columns], ["Warehouse", "Paddy Stock"])

	def test_the_disabled_column_is_still_added_when_asked_for(self):
		labels = [c["label"] for c in self.module.get_columns(frappe._dict(show_disabled_warehouses=1))]
		self.assertEqual(labels, ["Warehouse", "Paddy Stock", "Warehouse Disabled?"])

	def test_every_warehouse_shows_the_sum_of_its_grns_and_the_group_the_sum_of_its_children(self):
		self.rows([("GODOWN - SSPP", 157.258), ("GALI - SSPP", 78.0)])
		data = self.report_data()
		self.assertEqual(data["GODOWN - SSPP"], 157.258)
		self.assertEqual(data["GALI - SSPP"], 78.0)
		self.assertEqual(data["OPEN GODOWN - SSPP"], 0.0)  # no GRN names it
		self.assertEqual(data["All Warehouses - SSPP"], 235.258)  # ERPNext's own parent roll-up

	def test_another_companys_warehouses_do_not_receive_this_companys_paddy(self):
		self.rows([("GODOWN - SSPP", 157.258)])
		rgfp_tree = [warehouse("All Warehouses - RGFP", is_group=1), warehouse("GALI - RGFP", "All Warehouses - RGFP")]
		with patch.object(frappe, "get_all", MagicMock(return_value=[frappe._dict(w) for w in rgfp_tree]), create=True):
			data = {w.name: w.stock_balance for w in self.module.get_data(frappe._dict(company=RGFP))}
		self.assertEqual(data, {"All Warehouses - RGFP": 0.0, "GALI - RGFP": 0.0})

	def test_an_unloading_point_that_is_not_a_warehouse_is_not_counted(self):
		self.rows([("Warehouse 1", 71.188), ("GODOWN - SSPP", 10.0)])  # an older Quality Check holds free text
		data = self.report_data()
		self.assertEqual((data["GODOWN - SSPP"], data["All Warehouses - SSPP"]), (10.0, 10.0))
		self.assertNotIn("Warehouse 1", data)

	def test_the_stock_ledger_value_is_no_longer_used_for_the_column(self):
		self.rows([])
		self.assertEqual(set(self.report_data().values()), {0.0})

	def test_the_erpnext_tree_fields_are_kept(self):
		self.rows([("GODOWN - SSPP", 1.0)])
		with patch.object(frappe, "get_all", MagicMock(return_value=[frappe._dict(w) for w in SSPP_TREE]), create=True):
			rows = self.module.get_data(frappe._dict(company=SSPP))
		godown = next(w for w in rows if w.name == "GODOWN - SSPP")
		self.assertEqual((godown.parent_warehouse, godown.indent), ("All Warehouses - SSPP", 1))
		self.assertEqual(next(w for w in rows if w.name == "All Warehouses - SSPP").indent, 0)


class TestInstallAndUninstall(PaddyStockCase):
	def test_install_replaces_only_the_two_functions_and_remembers_the_originals(self):
		psr.install()
		self.assertIs(self.module.get_warehouse_wise_balance, psr.get_paddy_stock_by_warehouse)
		self.assertIsNot(self.module.get_columns, self.original[1])
		self.assertEqual(self.module._ivri_od_original, self.original)
		self.assertIs(self.module.execute.__module__ and self.module.get_data.__name__, "get_data")  # the rest is ERPNext's

	def test_installing_again_changes_nothing_further(self):
		psr.install()
		first = (self.module.get_warehouse_wise_balance, self.module.get_columns)
		psr.install()
		psr.install()
		self.assertEqual((self.module.get_warehouse_wise_balance, self.module.get_columns), first)
		self.assertEqual(self.module._ivri_od_original, self.original)

	def test_the_hooks_may_call_it_with_their_own_arguments(self):
		psr.install(method="x", kwargs={}, transaction_type="job")
		self.assertTrue(getattr(self.module, "_ivri_od_paddy_stock"))

	def test_uninstall_restores_erpnexts_own_functions(self):
		psr.install()
		psr.uninstall()
		self.assertEqual((self.module.get_warehouse_wise_balance, self.module.get_columns), self.original)
		self.assertFalse(hasattr(self.module, "_ivri_od_paddy_stock"))
		psr.uninstall()  # a second uninstall is harmless

	def test_without_the_install_erpnexts_report_is_as_it_was(self):
		self.assertEqual([c["label"] for c in self.module.get_columns(frappe._dict())], ["Warehouse", "Stock Balance"])

	def test_other_stock_reports_are_not_touched(self):
		psr.install()
		other = importlib.import_module("erpnext.stock.report.stock_balance.stock_balance")
		self.assertFalse(hasattr(other, "_ivri_od_paddy_stock"))
		item_age = importlib.import_module("erpnext.stock.report.warehouse_wise_item_balance_age_and_value.warehouse_wise_item_balance_age_and_value")
		self.assertFalse(hasattr(item_age, "_ivri_od_paddy_stock"))


class TestWiring(unittest.TestCase):
	def test_frappe_installs_it_for_requests_and_background_jobs(self):
		hooks = HOOKS.read_text()
		self.assertIn('before_request = ["ivri_od.procurement.paddy_stock_report.install"]', hooks)
		self.assertIn('before_job = ["ivri_od.procurement.paddy_stock_report.install"]', hooks)

	def test_the_source_uses_the_grn_and_quality_check_fields_and_never_the_stock_ledger(self):
		code = Path(psr.__file__).read_text()
		code = "\n".join(l for l in code.splitlines() if not l.lstrip().startswith("#"))
		body = code[code.index("def paddy_stock_query"): code.index("def get_paddy_stock_by_warehouse")]
		for field in ("GRN Note", "Quality Check", "net_weight", "quality_check", "unloading_point"):
			self.assertIn(field, body)
		self.assertNotIn("Stock Ledger Entry", body)
		self.assertNotIn("stock_value", body)

	def test_erpnexts_own_file_is_not_modified(self):
		path = Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "stock" / "report" / "warehouse_wise_stock_balance" / "warehouse_wise_stock_balance.py"
		text = path.read_text()
		self.assertIn('_("Stock Balance")', text)
		self.assertNotIn("Paddy", text)
		self.assertNotIn("ivri_od", text)


if __name__ == "__main__":
	unittest.main()
