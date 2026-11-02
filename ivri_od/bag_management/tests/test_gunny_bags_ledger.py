# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Gunny Bags Ledger rules and shape. Pure Python: no site, no database."""

import copy
import json
import re
import unittest
from pathlib import Path

import ivri_od
from ivri_od.bag_management.gunny_bags_ledger import build_ledger_rows, wbms_of_mill

ROOT = Path(ivri_od.__file__).resolve().parent
REPORT = ROOT / "bag_management/report/gunny_bags_ledger"
U1, U2 = "M1", "M2"
P1, P2 = "S1", "S2"
K1, K2, K3 = "M1-AAA(S1)-K25-TP1", "M1-AAA(S1)-K25-TP2", "M1-BBB(S2)-K25-TP3"
TPS = {
	K1: {"miller": "MILL ONE(M1)", "ppc": "AAA(S1)"},
	K2: {"miller": "MILL ONE(M1)", "ppc": "AAA(S1)"},  # a second Transit Pass of the same PPC
	K3: {"miller": "MILL ONE(M1)", "ppc": "BBB(S2)"},
}
PARTY = {K1: (U1, P1), K2: (U1, P1), K3: (U1, P2)}


def wbm(n, key=K1, qc=None, net=10.0, no_of_bags=536):
	"""A weighment. `no_of_bags` is the Transit Pass bag count copied onto it; the ledger must never use it."""
	return {"name": f"WBM-{n}", "pass_unique_key": key, "quality_check": qc if qc is not None else f"QC-{n}", "net_weight": net, "no_of_bags": no_of_bags}


def sent(unit=U1, ppc=P1, bags=0):
	return {"operating_unit": unit, "ppc": ppc, "bags_sent": bags}


def names(unit, ppc):
	return (f"MILL {unit}", f"PPC {ppc}")


def run(wbms, qcs=None, grns=None, sent_records=None, party=None, tps=None):
	"""qcs: physical bags by Quality Check name (default: 100 bags for every QC the weighments link)."""
	qcs = qcs if qcs is not None else {w["quality_check"]: 100 for w in wbms if w["quality_check"]}
	grns = grns if grns is not None else {w["name"] for w in wbms}
	return build_ledger_rows(
		wbms, dict(qcs), set(grns), TPS if tps is None else tps,
		party_of=PARTY if party is None else party, sent=sent_records, names_for=names,
	)


class TestCredit(unittest.TestCase):
	"""Credit Bags and Qty: completed trips only, bags from each trip's own Quality Check."""

	def test_a_trip_needs_both_its_qc_and_its_grn(self):
		a, b, c, d = wbm(1), wbm(2, qc=""), wbm(3), wbm(4)
		rows = run([a, b, c, d], qcs={"QC-1": 100, "QC-3": 100, "QC-4": 100}, grns={"WBM-1", "WBM-2", "WBM-4"})
		# WBM-1 has both; WBM-2 has no QC; WBM-3 has no GRN; WBM-4 has both
		self.assertEqual((rows[0]["qty"], rows[0]["credit_bags"]), (20.0, 200))

	def test_a_link_to_a_qc_that_does_not_exist_is_not_a_completed_trip(self):
		self.assertEqual(run([wbm(1)], qcs={}), [])

	def test_qty_and_credit_are_summed_over_completed_trips_only(self):
		rows = run(
			[wbm(1, net=86.07), wbm(2, net=71.188), wbm(3, net=5.0)],
			qcs={"QC-1": 196, "QC-2": 177, "QC-3": 7},
			grns={"WBM-1", "WBM-2"},
		)
		self.assertEqual((rows[0]["qty"], rows[0]["credit_bags"]), (157.258, 373))

	def test_two_weighments_on_one_qc_are_two_trips_and_each_adds_that_qcs_bags(self):
		rows = run([wbm(1, qc="QC-X"), wbm(2, qc="QC-X")], qcs={"QC-X": 196})
		self.assertEqual((rows[0]["qty"], rows[0]["credit_bags"]), (20.0, 392))

	def test_several_grns_for_one_wbm_count_the_trip_and_its_bags_once(self):
		rows = run([wbm(1)], qcs={"QC-1": 196}, grns={"WBM-1", "WBM-1"})
		self.assertEqual((rows[0]["qty"], rows[0]["credit_bags"]), (10.0, 196))

	def test_the_same_wbm_listed_twice_is_counted_once(self):
		a = wbm(1)
		rows = run([a, dict(a)], qcs={"QC-1": 196})
		self.assertEqual((rows[0]["qty"], rows[0]["credit_bags"]), (10.0, 196))

	def test_bags_come_from_the_quality_check_not_the_weighments_transit_pass_count(self):
		rows = run([wbm(1, no_of_bags=536), wbm(2, no_of_bags=536)], qcs={"QC-1": 196, "QC-2": 177})
		self.assertEqual(rows[0]["credit_bags"], 373)

	def test_a_qc_with_no_bags_adds_none(self):
		self.assertEqual(run([wbm(1)], qcs={"QC-1": 0})[0]["credit_bags"], 0)

	def test_tp339_gives_569_credit_bags_not_1608(self):
		"""The live records: WBM-103 and WBM-104 both link QC-124 (196 bags), WBM-105 links QC-125 (177)."""
		key = "M051007-MALMANDA(S1051105)-K25-TP339"
		wbms = [
			wbm(103, key, qc="QC-2026-124", net=71.188),
			wbm(104, key, qc="QC-2026-124", net=86.07),
			wbm(105, key, qc="QC-2026-125", net=78.0),
		]
		tps = {key: {"miller": "SHREE SHYAMJI PADDY PROCESSING PVT LTD(M051007)", "ppc": "MALMANDA(S1051105)"}}
		rows = build_ledger_rows(
			wbms, {"QC-2026-124": 196, "QC-2026-125": 177}, {"WBM-103", "WBM-104", "WBM-105"}, tps,
			party_of={key: ("M051007", "S1051105")},
		)
		self.assertEqual((rows[0]["qty"], rows[0]["credit_bags"]), (235.258, 569))
		self.assertNotEqual(rows[0]["credit_bags"], 1608)

	def test_tp211_gives_425_credit_bags_not_the_transit_pass_426(self):
		key = "M051007-BATASANA(MY200713)-R25-TP211"
		rows = build_ledger_rows(
			[wbm(97, key, qc="QC-2026-120", net=158.33, no_of_bags=426)], {"QC-2026-120": 425}, {"WBM-97"}, {},
			party_of={key: ("M051007", "MY200713")},
		)
		self.assertEqual((rows[0]["qty"], rows[0]["credit_bags"]), (158.33, 425))
		self.assertNotEqual(rows[0]["credit_bags"], 426)


class TestGroupingByMillAndPpc(unittest.TestCase):
	def test_two_transit_passes_of_one_ppc_are_one_row(self):
		rows = run([wbm(1, K1, net=10), wbm(2, K2, net=15)], qcs={"QC-1": 100, "QC-2": 50})
		self.assertEqual(len(rows), 1)
		self.assertEqual((rows[0]["mill_name"], rows[0]["ppc_name"], rows[0]["qty"], rows[0]["credit_bags"]), ("MILL ONE(M1)", "AAA(S1)", 25.0, 150))

	def test_different_ppcs_are_different_rows(self):
		rows = run([wbm(1, K1), wbm(2, K3)])
		self.assertEqual([r["ppc_name"] for r in rows], ["AAA(S1)", "BBB(S2)"])

	def test_the_same_ppc_under_two_mills_is_two_rows(self):
		rows = run([wbm(1, K1), wbm(2, K2)], party={K1: (U1, P1), K2: (U2, P1)})
		self.assertEqual(len(rows), 2)

	def test_rows_without_a_pass_unique_key_are_left_out(self):
		self.assertEqual(run([wbm(1, key=""), wbm(2, key="   ")]), [])

	def test_a_pass_whose_ppc_is_not_in_the_masters_is_grouped_by_its_text_and_has_no_debit(self):
		rows = run([wbm(1, K1), wbm(2, K1)], party={K1: (U1, None)}, sent_records=[sent(U1, P1, 500)])
		unmatched = next(r for r in rows if r["ppc_name"] == "AAA(S1)")
		self.assertEqual((unmatched["credit_bags"], unmatched["debit_bags"]), (200, 0))

	def test_no_transit_pass_gives_blank_names_but_still_counts(self):
		rows = build_ledger_rows([wbm(1, key="UNKNOWN")], {"QC-1": 40}, {"WBM-1"}, {})
		self.assertEqual((rows[0]["mill_name"], rows[0]["ppc_name"], rows[0]["credit_bags"]), ("", "", 40))


class TestDebit(unittest.TestCase):
	"""Debit Bags: the Number of Bags Sent of the submitted records of the same Mill + PPC."""

	def test_debit_is_the_number_of_bags_sent_to_that_ppc(self):
		rows = run([wbm(1, K1)], sent_records=[sent(U1, P1, 2000)])
		self.assertEqual((rows[0]["debit_bags"], rows[0]["credit_bags"]), (2000, 100))

	def test_several_sent_records_of_one_ppc_are_added(self):
		rows = run([wbm(1, K1)], sent_records=[sent(U1, P1, 2000), sent(U1, P1, 500)])
		self.assertEqual(rows[0]["debit_bags"], 2500)

	def test_debit_is_counted_once_however_many_transit_passes_the_ppc_has(self):
		rows = run([wbm(1, K1), wbm(2, K2)], sent_records=[sent(U1, P1, 2000)])
		self.assertEqual(len(rows), 1)
		self.assertEqual(sum(r["debit_bags"] for r in rows), 2000)

	def test_debit_goes_only_to_its_own_ppc_and_mill(self):
		rows = run([wbm(1, K1), wbm(2, K3)], sent_records=[sent(U1, P1, 2000), sent(U2, P1, 300)])
		by_ppc = {(r["mill_name"], r["ppc_name"]): r["debit_bags"] for r in rows}
		self.assertEqual(by_ppc[("MILL ONE(M1)", "AAA(S1)")], 2000)
		self.assertEqual(by_ppc[("MILL ONE(M1)", "BBB(S2)")], 0)
		self.assertEqual(by_ppc[("MILL M2", "PPC S1")], 300)  # other mill, no trips: a row of its own

	def test_a_ppc_with_bags_sent_but_no_completed_trip_still_has_a_row(self):
		rows = run([], sent_records=[sent(U1, P2, 750)])
		self.assertEqual(rows, [{"mill_name": "MILL M1", "ppc_name": "PPC S2", "qty": 0.0, "debit_bags": 750, "credit_bags": 0, "remaining_bags": 750}])

	def test_without_sent_records_debit_is_zero(self):
		self.assertEqual(run([wbm(1)])[0]["debit_bags"], 0)

	def test_a_sent_record_without_a_ppc_or_mill_is_ignored(self):
		self.assertEqual(run([], sent_records=[sent("", P1, 5), sent(U1, "", 5)]), [])

	def test_rows_have_exactly_the_six_ledger_values(self):
		row = run([wbm(1)], sent_records=[sent(U1, P1, 1)])[0]
		self.assertEqual(set(row), {"mill_name", "ppc_name", "qty", "debit_bags", "credit_bags", "remaining_bags"})
		self.assertNotIn("trips", row)

	def test_inputs_are_not_changed(self):
		items, qcs, records = [wbm(1), wbm(2)], {"QC-1": 5, "QC-2": 6}, [sent(U1, P1, 9)]
		before = copy.deepcopy((items, qcs, records))
		run(items, qcs=qcs, sent_records=records)
		self.assertEqual((items, qcs, records), before)


class TestRemaining(unittest.TestCase):
	"""Remaining Bags = Debit Bags - Credit Bags, only on a row that has Debit Bags, never negative."""

	def test_remaining_is_debit_minus_credit_when_there_is_debit(self):
		row = run([wbm(1, K1)], qcs={"QC-1": 456}, sent_records=[sent(U1, P1, 2000)])[0]
		self.assertEqual((row["debit_bags"], row["credit_bags"], row["remaining_bags"]), (2000, 456, 1544))

	def test_all_bags_returned_shows_zero(self):
		row = run([wbm(1, K1)], qcs={"QC-1": 500}, sent_records=[sent(U1, P1, 500)])[0]
		self.assertEqual(row["remaining_bags"], 0)

	def test_more_returned_than_sent_shows_zero_never_a_negative_number(self):
		row = run([wbm(1, K1)], qcs={"QC-1": 569}, sent_records=[sent(U1, P1, 100)])[0]
		self.assertEqual((row["debit_bags"], row["credit_bags"], row["remaining_bags"]), (100, 569, 0))

	def test_no_debit_leaves_remaining_empty(self):
		row = run([wbm(1, K1)], qcs={"QC-1": 690})[0]
		self.assertEqual((row["debit_bags"], row["credit_bags"]), (0, 690))
		self.assertIsNone(row["remaining_bags"])

	def test_a_ppc_with_bags_sent_and_no_trip_has_all_of_them_remaining(self):
		self.assertEqual(run([], sent_records=[sent(U1, P2, 750)])[0]["remaining_bags"], 750)

	def test_all_transit_passes_of_a_ppc_count_against_its_one_debit(self):
		rows = run([wbm(1, K1), wbm(2, K2)], qcs={"QC-1": 100, "QC-2": 50}, sent_records=[sent(U1, P1, 400)])
		self.assertEqual((len(rows), rows[0]["credit_bags"], rows[0]["remaining_bags"]), (1, 150, 250))

	def test_no_row_ever_has_a_negative_remaining(self):
		rows = run(
			[wbm(1, K1), wbm(2, K3)], qcs={"QC-1": 100, "QC-2": 70},
			sent_records=[sent(U1, P1, 40), sent(U1, P2, 900)],
		)
		self.assertTrue(all(r["remaining_bags"] is None or r["remaining_bags"] >= 0 for r in rows))
		self.assertEqual([r["remaining_bags"] for r in rows], [0, 830])

	def test_a_row_is_filled_exactly_when_it_has_debit(self):
		rows = run([wbm(1, K1), wbm(2, K3)], qcs={"QC-1": 100, "QC-2": 70}, sent_records=[sent(U1, P1, 400)])
		for r in rows:
			self.assertEqual(r["remaining_bags"] is not None, r["debit_bags"] > 0)

	def test_the_other_values_are_unchanged_by_the_rule(self):
		row = run([wbm(1, K1, net=10)], qcs={"QC-1": 100}, sent_records=[sent(U1, P1, 40)])[0]
		self.assertEqual((row["qty"], row["debit_bags"], row["credit_bags"], row["remaining_bags"]), (10.0, 40, 100, 0))


class TestReportShape(unittest.TestCase):
	def setUp(self):
		self.source = (REPORT / "gunny_bags_ledger.py").read_text()

	def test_report_is_registered_with_one_role(self):
		meta = json.loads((REPORT / "gunny_bags_ledger.json").read_text())
		self.assertEqual((meta["report_type"], meta["ref_doctype"], [r["role"] for r in meta["roles"]]), ("Script Report", "Weigh Bridge Measurement", ["System Manager"]))

	def test_columns_are_mill_ppc_qty_debit_credit_and_remaining_in_that_order(self):
		labels = re.findall(r'"label": _\("([^"]+)"\)', self.source)
		self.assertEqual(labels, ["Mill Name", "PPC Name", "Qty", "Debit Bags", "Credit Bags", "Remaining Bags"])
		self.assertNotIn("No. of Trips", self.source)
		self.assertNotIn("No. of Received Bags", self.source)

	def test_debit_reads_only_submitted_gunny_bags_sent_records_of_the_selected_mill(self):
		self.assertIn('"Gunny Bags Sent to PPC"', self.source)
		self.assertIn('"docstatus": 1, "operating_unit": mill', self.source)
		self.assertIn("bags_sent", self.source)

	def test_credit_reads_bags_from_the_quality_check_only(self):
		self.assertIn("paddy_received_in_pkt", self.source)
		self.assertNotIn("no_of_bags", self.source)
		self.assertNotIn("no_of_bags", (ROOT / "bag_management/gunny_bags_ledger.py").read_text())

	def test_navigation_lists_the_report_and_the_existing_doctype_only(self):
		ws = json.loads((ROOT / "bag_management/workspace/bag_management/bag_management.json").read_text())
		self.assertEqual([(s["type"], s["link_to"]) for s in ws["shortcuts"]], [("DocType", "Gunny Bags Sent to PPC"), ("Report", "Gunny Bags Ledger")])


class TestMillSelection(unittest.TestCase):
	"""The ledger is for one Mill Master. Its weighments and sent records are the only ones used."""

	def test_only_the_selected_mills_weighments_are_kept(self):
		party = {K1: (U1, P1), K3: ("M9", P1)}
		kept = wbms_of_mill([wbm(1, K1), wbm(2, K3)], party, U1)
		self.assertEqual([w["name"] for w in kept], ["WBM-1"])

	def test_a_pass_whose_mill_is_not_in_the_masters_belongs_to_no_mill(self):
		self.assertEqual(wbms_of_mill([wbm(1, K1)], {K1: (None, P1)}, U1), [])
		self.assertEqual(wbms_of_mill([wbm(1, K1)], {}, U1), [])

	def test_no_mill_selected_keeps_nothing(self):
		self.assertEqual(wbms_of_mill([wbm(1, K1)], PARTY, ""), [])
		self.assertEqual(wbms_of_mill([wbm(1, K1)], PARTY, None), [])

	def test_totals_use_only_the_selected_mill(self):
		party = {K1: (U1, P1), K3: (U2, P2)}
		both = [wbm(1, K1, net=10), wbm(2, K3, net=99)]
		qcs = {"QC-1": 100, "QC-2": 7}
		rows = build_ledger_rows(wbms_of_mill(both, party, U1), qcs, {"WBM-1", "WBM-2"}, TPS, party_of=party, sent=[sent(U1, P1, 40)], names_for=names)
		self.assertEqual([(r["qty"], r["debit_bags"], r["credit_bags"]) for r in rows], [(10.0, 40, 100)])
		self.assertEqual((sum(r["qty"] for r in rows), sum(r["debit_bags"] for r in rows), sum(r["credit_bags"] for r in rows)), (10.0, 40, 100))

	def test_the_report_calculation_is_otherwise_unchanged_for_the_selected_mill(self):
		"""Same rows as the combined calculation, restricted to one mill."""
		party = {K1: (U1, P1), K3: (U2, P2)}
		wbms = [wbm(1, K1, net=10), wbm(2, K3, net=99)]
		qcs, grns = {"QC-1": 100, "QC-2": 7}, {"WBM-1", "WBM-2"}
		combined = build_ledger_rows(wbms, qcs, grns, TPS, party_of=party, names_for=names)
		one = build_ledger_rows(wbms_of_mill(wbms, party, U1), qcs, grns, TPS, party_of=party, names_for=names)
		self.assertEqual(one, [r for r in combined if r["ppc_name"] == "AAA(S1)"])


class TestReportWithoutAMill(unittest.TestCase):
	def setUp(self):
		import frappe
		from unittest.mock import MagicMock, patch

		from ivri_od.bag_management.report.gunny_bags_ledger import gunny_bags_ledger as report

		frappe.local.lang = "en"
		self.frappe, self.report = frappe, report
		self.db = MagicMock()
		for target, value in (("db", self.db),):
			patcher = patch.object(frappe, target, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		patcher = patch.object(report, "get_data", return_value=[{"ppc_name": "x"}])
		self.get_data = patcher.start()
		self.addCleanup(patcher.stop)

	def test_no_mill_gives_a_prompt_and_no_rows(self):
		for filters in (None, {}, {"mill": ""}, {"mill": "   "}):
			columns, data, message = self.report.execute(filters)
			self.assertEqual(data, [])
			self.assertIn("Select a Mill Name", message)
		self.get_data.assert_not_called()
		self.db.exists.assert_not_called()

	def test_the_columns_are_still_returned_without_a_mill(self):
		self.assertEqual([c["fieldname"] for c in self.report.execute({})[0]], ["mill_name", "ppc_name", "qty", "debit_bags", "credit_bags", "remaining_bags"])

	def test_a_selected_mill_is_calculated(self):
		self.db.exists.return_value = True
		columns, data = self.report.execute({"mill": "M051007"})
		self.assertEqual(data, [{"ppc_name": "x"}])
		self.get_data.assert_called_once_with("M051007")
		self.db.exists.assert_called_once_with("Mill Master", "M051007")

	def test_an_unknown_mill_is_refused(self):
		from unittest.mock import patch

		self.db.exists.return_value = False
		# frappe.throw needs a bound site (message queue); the decision to refuse is what is tested here
		with patch.object(self.frappe, "throw", side_effect=self.frappe.ValidationError("Mill NOPE was not found")) as thrown:
			with self.assertRaises(self.frappe.ValidationError):
				self.report.execute({"mill": "NOPE"})
		self.assertIn("was not found in Mill Master", thrown.call_args.args[0])
		self.get_data.assert_not_called()


NODE_HARNESS = r"""
const fs = require("fs");
const file = process.argv.slice(-1)[0];
const frappe = { query_reports: {} };
const __ = (s) => s;
new Function("frappe", "__", fs.readFileSync(file, "utf8"))(frappe, __);
console.log(JSON.stringify(frappe.query_reports["Gunny Bags Ledger"].filters));
"""


def _node():
	import glob
	import os
	import shutil

	found = shutil.which("node")
	if found:
		return found
	matches = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
	return matches[-1] if matches else None


@unittest.skipUnless(_node(), "Node is not installed")
class TestMillNameFilter(unittest.TestCase):
	def test_there_is_one_required_mill_name_filter_fed_from_mill_master(self):
		import subprocess

		out = subprocess.run([_node(), "-e", NODE_HARNESS, str(REPORT / "gunny_bags_ledger.js")], capture_output=True, text=True, check=True)
		filters = json.loads(out.stdout)
		self.assertEqual(len(filters), 1)
		f = filters[0]
		self.assertEqual((f["fieldname"], f["label"], f["fieldtype"], f["options"], f["reqd"]), ("mill", "Mill Name", "Link", "Mill Master", 1))
		self.assertNotIn("default", f)

	def test_no_mill_is_hardcoded(self):
		source = (REPORT / "gunny_bags_ledger.js").read_text()
		for code in ("M050410", "M050414", "M050415", "M050421", "M051007", "Shyamji", "Radhe", "Laddu"):
			self.assertNotIn(code, source)
		self.assertNotIn("M0", (REPORT / "gunny_bags_ledger.py").read_text().replace("M051007", ""))


FULL_NAME = "Shree Shyamji Paddy Processing Pvt Ltd (Boiled)"


class TestFullMillName(unittest.TestCase):
	def test_every_row_shows_the_full_mill_name_not_the_transit_pass_text(self):
		rows = run([wbm(1, K1), wbm(2, K3)], sent_records=[sent(U1, P2, 5)]) and build_ledger_rows(
			[wbm(1, K1), wbm(2, K3)], {"QC-1": 100, "QC-2": 70}, {"WBM-1", "WBM-2"}, TPS,
			party_of=PARTY, sent=[sent(U1, "S9", 5)], names_for=names, mill_name=FULL_NAME,
		)
		self.assertTrue(rows)
		self.assertEqual({r["mill_name"] for r in rows}, {FULL_NAME})
		self.assertTrue(all("(M1)" not in r["mill_name"] for r in rows))

	def test_a_row_that_exists_only_through_a_sent_record_has_the_same_name(self):
		rows = build_ledger_rows([], {}, set(), TPS, sent=[sent(U1, P1, 40)], names_for=names, mill_name=FULL_NAME)
		self.assertEqual([r["mill_name"] for r in rows], [FULL_NAME])

	def test_the_name_changes_nothing_else(self):
		args = ([wbm(1, K1, net=10)], {"QC-1": 100}, {"WBM-1"}, TPS)
		plain = build_ledger_rows(*args, party_of=PARTY, sent=[sent(U1, P1, 40)], names_for=names)[0]
		named = build_ledger_rows(*args, party_of=PARTY, sent=[sent(U1, P1, 40)], names_for=names, mill_name=FULL_NAME)[0]
		self.assertEqual({k: v for k, v in plain.items() if k != "mill_name"}, {k: v for k, v in named.items() if k != "mill_name"})

	def test_without_a_name_the_transit_pass_text_is_used_as_before(self):
		self.assertEqual(run([wbm(1, K1)])[0]["mill_name"], "MILL ONE(M1)")


class TestMillFullNameLookup(unittest.TestCase):
	def setUp(self):
		import frappe
		from unittest.mock import MagicMock, patch

		from ivri_od.bag_management.report.gunny_bags_ledger import gunny_bags_ledger as report

		self.report = report
		self.db = MagicMock()
		patcher = patch.object(frappe, "db", self.db, create=True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_the_display_name_is_used_in_full(self):
		self.db.get_value.return_value = {"display_name": FULL_NAME, "company": "Other"}
		self.assertEqual(self.report.mill_full_name("M051007"), FULL_NAME)

	def test_the_company_name_is_used_when_there_is_no_display_name(self):
		self.db.get_value.return_value = {"display_name": "  ", "company": "Laddu Gopal Industries (Boiled)"}
		self.assertEqual(self.report.mill_full_name("M050421"), "Laddu Gopal Industries (Boiled)")

	def test_the_code_is_the_last_resort(self):
		self.db.get_value.return_value = None
		self.assertEqual(self.report.mill_full_name("M0"), "M0")

	def test_the_name_is_read_from_mill_master(self):
		self.db.get_value.return_value = {"display_name": FULL_NAME}
		self.report.mill_full_name("M051007")
		self.assertEqual(self.db.get_value.call_args.args[:2], ("Mill Master", "M051007"))

	def test_the_mill_name_column_is_wide_enough_for_a_full_name(self):
		source = (REPORT / "gunny_bags_ledger.py").read_text()
		width = int(re.search(r'"fieldname": "mill_name", "fieldtype": "Data", "width": (\d+)', source).group(1))
		self.assertGreaterEqual(width, 400)


ONLOAD_HARNESS = r"""
const fs = require("fs");
const file = process.argv.slice(-1)[0];
const calls = [];
const frappe = { query_reports: {} };
const __ = (s) => s;
const $ = (el) => ({
	removeClass(c) { calls.push(["removeClass", c]); return this; },
	css(o) { calls.push(["css", o]); return this; },
});
new Function("frappe", "__", "$", fs.readFileSync(file, "utf8"))(frappe, __, $);
const settings = frappe.query_reports["Gunny Bags Ledger"];
const wrapper = {};
settings.onload({ get_filter: (name) => (name === "mill" ? { wrapper } : undefined) });
settings.onload({ get_filter: () => undefined });  // no such filter: must not fail
console.log(JSON.stringify(calls));
"""


@unittest.skipUnless(_node(), "Node is not installed")
class TestMillFilterIsWideEnough(unittest.TestCase):
	def test_the_mill_filter_loses_its_narrow_column_and_gets_a_wide_one(self):
		import subprocess

		out = subprocess.run([_node(), "-e", ONLOAD_HARNESS, str(REPORT / "gunny_bags_ledger.js")], capture_output=True, text=True, check=True)
		calls = json.loads(out.stdout)
		self.assertEqual(calls[0], ["removeClass", "col-md-2"])
		css = calls[1][1]
		self.assertGreaterEqual(int(css["width"].rstrip("px")), 400)
		self.assertEqual(len(calls), 2)  # the second onload, without the filter, did nothing
