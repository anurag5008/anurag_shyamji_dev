# Copyright (c) 2026, Profezzo and Contributors
# See license.txt
"""The Weigh Bridge form decides when to rebuild its Bag Details from the Quality Check.

The two decision functions are taken from weigh_bridge_measurement.js as they are and run in Node, with a
stub for the form. The tests are skipped when Node is not installed. No site, no database.
"""

import glob
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "doctype/weigh_bridge_measurement/weigh_bridge_measurement.js"

HARNESS = r"""
const fs = require("fs");
const vm = require("vm");
const [file, casesJson] = process.argv.slice(-2);  // node -e has no script path in argv
const source = fs.readFileSync(file, "utf8");
function extract(name) {
	const start = source.indexOf(`function ${name}(`);
	if (start < 0) throw new Error(`function ${name} not found`);
	const end = source.indexOf("\n}\n", start);
	return source.slice(start, end + 2);
}
const sandbox = { cint: (v) => parseInt(v || 0, 10) || 0 };
vm.createContext(sandbox);
vm.runInContext(extract("bag_table_needs_qc_sync") + "\n" + extract("should_refresh_bags_from_qc"), sandbox);
const cases = JSON.parse(casesJson);
const out = cases.map((c) => {
	const frm = { doc: { bag_weight_details: c.rows }, _wbm_qc_bag_modified: c.marker };
	const data = { quality_check: c.qc, bag_details: c.details, qc_modified: c.modified };
	return sandbox.should_refresh_bags_from_qc(frm, data);
});
console.log(JSON.stringify(out));
"""


def _node():
	found = shutil.which("node")
	if found:
		return found
	matches = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
	return matches[-1] if matches else None


def row(jute=0, plastic=0):
	return {"jute_bags": jute, "plastic_bags": plastic}


@unittest.skipUnless(_node(), "Node is not installed")
class TestFormBagRefreshDecision(unittest.TestCase):
	def refresh(self, rows, qc, details, marker="", modified=""):
		case = {"rows": rows, "qc": qc, "details": details, "marker": marker, "modified": modified}
		result = subprocess.run(
			[_node(), "-e", HARNESS, str(JS), json.dumps([case])], capture_output=True, text=True, check=True
		)
		return json.loads(result.stdout)[0]

	def test_a_qc_that_appears_after_the_form_loaded_fills_the_empty_table(self):
		self.assertTrue(self.refresh([], "QC-1", [row(120, 48)]))

	def test_a_changed_qc_with_other_counts_rebuilds_the_table(self):
		self.assertTrue(self.refresh([row(0, 168)], "QC-2", [row(150, 0)]))

	def test_a_different_number_of_lines_rebuilds_the_table(self):
		self.assertTrue(self.refresh([row(10, 0)], "QC-1", [row(10, 0), row(0, 5)]))

	def test_a_table_that_already_matches_is_left_alone(self):
		self.assertFalse(self.refresh([row(120, 48)], "QC-1", [row(120, 48)], marker="t1", modified="t1"))

	def test_the_table_is_emptied_when_the_weighment_has_no_qc_any_more(self):
		self.assertTrue(self.refresh([row(150, 0)], "", []))

	def test_the_table_is_emptied_when_the_qc_has_no_bag_lines(self):
		self.assertTrue(self.refresh([row(150, 0)], "QC-LEGACY", []))

	def test_an_empty_table_with_no_qc_needs_nothing(self):
		self.assertFalse(self.refresh([], "", []))

	def test_an_empty_table_with_a_qc_without_lines_needs_nothing(self):
		self.assertFalse(self.refresh([], "QC-LEGACY", []))


if __name__ == "__main__":
	unittest.main()
