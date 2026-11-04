# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Gate Exit: the Vehicle No is read from the Gate Entry pass QR text. Node tests of the form script, no site data."""

import glob
import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "doctype" / "gate_exit" / "gate_exit.js"
QR = "Vehicle No: CG04 ab1234\\nParty Name: Test Party\\nDriver Name: Ram\\nMobile No: 9999999999\\nPurpose: Unload"


def _node():
	found = shutil.which("node")
	if found:
		return found
	matches = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
	return matches[-1] if matches else None


HARNESS = r"""
const fs = require("fs");
let handlers, buttons = [], dialogs = [], alerts = [], calls = [], saves = 0, call_result;
const frappe = {
	ui: { form: { on(dt, h) { handlers = h; } }, Dialog: class { constructor(o) { this.o = o; this.v = {}; o.fields.forEach((f) => { if (f.default) this.v[f.fieldname] = f.default; }); dialogs.push(this); this.hidden = false; }
		show() {} hide() { this.hidden = true; } get_value(k) { return this.v[k]; } set_value(k, v) { this.v[k] = v; }
		get_field() { return { $wrapper: { addClass() { return this; }, html() {} } }; } },
		Scanner: class { constructor(o) { this.o = o; } scan() {} stop_scan() {} } },
	show_alert(a) { alerts.push(a.indicator); },
	msgprint() {},
	call(o) { calls.push(o.method); o.callback({ message: call_result }); },
};
global.__ = (s) => s;
global.window = { isSecureContext: true }; global.navigator = { mediaDevices: {} };
new Function("frappe", fs.readFileSync(process.argv.slice(-1)[0], "utf8"))(frappe);
const QR = process.argv[process.argv.length - 2];
const make = (doc = {}) => {
	const frm = { doc, fields_dict: {}, inside_mill_vehicles: ["CG04AB1234"], saved: 0, is_new: () => true,
		add_custom_button(l, f) { buttons.push([l, f]); },
		set_value(k, v) { const changed = this.doc[k] !== v; this.doc[k] = v; if (changed && handlers[k]) handlers[k](this); }, save() { saves += 1; } };
	return frm;
};
const open = (frm) => { buttons = []; handlers.refresh(frm); buttons[0][1](); const d = dialogs[dialogs.length - 1]; d.o.on_page_show(); return d; };
const scan = (d, text) => { d.v.scanned_text = text; d.o.fields.find((f) => f.fieldname === "scanned_text").change.call(d); };
const found = { gate_entry_in: "GE-1", vehicle_no: "CG04AB1234", driver_name: "Ram" };
const out = {};
let frm = make(); call_result = found;
handlers.refresh(frm); out.button = buttons.map((b) => b[0]);
let d = open(frm);
out.title = d.o.title; out.purpose_options = d.o.fields[0].options;
// 1. no purpose chosen: nothing happens
scan(d, QR); out.no_purpose = { vehicle: frm.doc.vehicle_no || null, saves, closed: d.hidden, alerts: alerts.slice() };
// 2. purpose chosen: vehicle filled and saved once
d.v.out_purpose = "FCI DEPO"; calls.length = 0; scan(d, QR);
out.saved = { vehicle: frm.doc.vehicle_no, purpose: frm.doc.out_purpose, gate_entry_in: frm.doc.gate_entry_in, driver: frm.doc.driver_name, saves, closed: d.hidden, resolve_calls: calls.length };
// 3. Others needs details
frm = make(); saves = 0; d = open(frm); d.v.out_purpose = "Others"; scan(d, QR);
out.others_no_detail = { vehicle: frm.doc.vehicle_no || null, saves };
d.v.out_purpose_detail = " Sold to buyer "; scan(d, QR);
out.others_with_detail = { detail: frm.doc.out_purpose_detail, saves };
// 4. vehicle not inside the mill (server says so): no save
frm = make(); saves = 0; call_result = { error: "not inside" }; d = open(frm); d.v.out_purpose = "RRC DEPO"; scan(d, QR);
out.not_inside = { saves, save_flag: !!frm.save_after_scan, gate_entry_in: frm.doc.gate_entry_in };
// 5. vehicle missing from the inside list: no save
frm = make(); saves = 0; frm.inside_mill_vehicles = ["OTHER"]; call_result = found; d = open(frm); d.v.out_purpose = "RRC DEPO"; scan(d, QR);
out.not_in_list = { saves, save_flag: !!frm.save_after_scan };
// 6. wrong QR: nothing
frm = make(); saves = 0; d = open(frm); d.v.out_purpose = "RRC DEPO"; scan(d, "hello");
out.wrong_qr = { vehicle: frm.doc.vehicle_no || null, saves, closed: d.hidden };
// 7. picking the vehicle by hand never saves
frm = make(); saves = 0; call_result = found; handlers.vehicle_no.call(null, (frm.doc.vehicle_no = "CG04AB1234", frm));
out.manual_pick_saves = saves;
// 8. the same vehicle already in the form is saved too
frm = make({ vehicle_no: "CG04AB1234" }); saves = 0; d = open(frm); d.v.out_purpose = "FCI DEPO"; scan(d, QR);
out.same_vehicle = { saves };
// 9. purpose of the form is offered in the window
frm = make({ out_purpose: "RRC DEPO" }); d = open(frm); out.prefilled = d.v.out_purpose;
// saved document: no button
frm = make(); frm.is_new = () => false; buttons = []; handlers.refresh(frm); out.saved_doc_buttons = buttons.length;
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(_node(), "Node is not installed")
class TestGateExitScan(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		out = subprocess.run([_node(), "-e", HARNESS, QR.replace("\\n", "\n"), str(JS)], capture_output=True, text=True, check=True)
		cls.r = json.loads(out.stdout)

	def test_a_new_gate_exit_has_a_scan_button_and_a_saved_one_has_none(self):
		self.assertEqual(self.r["button"], ["Scan QR"])
		self.assertEqual(self.r["saved_doc_buttons"], 0)

	def test_the_window_asks_for_the_out_purpose_with_the_same_options_as_the_form(self):
		self.assertEqual(self.r["purpose_options"], "\nFCI DEPO\nRRC DEPO\nOthers")
		self.assertEqual(self.r["prefilled"], "RRC DEPO")

	def test_a_good_scan_fills_the_form_and_saves_it_once(self):
		saved = self.r["saved"]
		self.assertEqual((saved["vehicle"], saved["purpose"], saved["gate_entry_in"], saved["driver"]), ("CG04AB1234", "FCI DEPO", "GE-1", "Ram"))
		self.assertEqual(saved["saves"], 1)
		self.assertTrue(saved["closed"])

	def test_the_vehicle_is_found_once_not_twice(self):
		self.assertEqual(self.r["saved"]["resolve_calls"], 1)

	def test_without_an_out_purpose_nothing_is_filled_or_saved(self):
		self.assertEqual(self.r["no_purpose"], {"vehicle": None, "saves": 0, "closed": False, "alerts": ["orange"]})

	def test_others_needs_purpose_details_before_the_save(self):
		self.assertEqual(self.r["others_no_detail"], {"vehicle": None, "saves": 0})
		self.assertEqual(self.r["others_with_detail"], {"detail": "Sold to buyer", "saves": 1})

	def test_a_vehicle_that_is_not_inside_the_mill_is_not_saved(self):
		self.assertEqual(self.r["not_inside"], {"saves": 0, "save_flag": False, "gate_entry_in": ""})
		self.assertEqual(self.r["not_in_list"], {"saves": 0, "save_flag": False})

	def test_a_wrong_qr_is_refused_and_nothing_is_saved(self):
		self.assertEqual(self.r["wrong_qr"], {"vehicle": None, "saves": 0, "closed": False})

	def test_picking_the_vehicle_by_hand_does_not_save(self):
		self.assertEqual(self.r["manual_pick_saves"], 0)

	def test_a_scan_of_the_vehicle_already_in_the_form_is_saved_too(self):
		self.assertEqual(self.r["same_vehicle"], {"saves": 1})

	def test_the_qr_built_by_gate_entry_has_the_vehicle_line_the_scan_reads(self):
		from ivri_od.procurement.pass_print import qr_content_gate_entry

		class Doc:
			vehicle_no, driver_name, mobile_no, in_out, in_purpose, out_purpose = "CG04AB1234", "Ram", "", "In", "Unload", ""

		self.assertIn("Vehicle No: CG04AB1234", qr_content_gate_entry(Doc(), "").splitlines())


if __name__ == "__main__":
	unittest.main()
