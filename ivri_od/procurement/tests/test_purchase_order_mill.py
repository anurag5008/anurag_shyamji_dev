# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

"""Purchase Order rice mill fields: hamali, manual quantities, transport rules, field definitions.

Mocked tests: no site data is read or written.
"""

import glob
import json
import os
import shutil
import subprocess
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from ivri_od.procurement import purchase_order_mill as po

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "custom_field.json"
HOOKS = ROOT / "hooks.py"
JS = ROOT / "public" / "js" / "purchase_order_mill.js"


class FakeDoc(dict):
	"""A document as far as the validation needs it."""

	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value

	def set(self, key, value):
		self[key] = value

	def precision(self, fieldname):
		return 2

	def get_doc_before_save(self):
		return None


def rows(*pairs):
	"""Items rows as (uom, qty) pairs."""
	return [{"uom": uom, "qty": qty, "avg_wt": 25, "rate": 100} for uom, qty in pairs]


def doc(bags=0, **values):
	"""A Purchase Order whose Items hold `bags` of quantity in Bags (and a Quintal row that must not count)."""
	base = {"items": rows(("Quintal", 50), ("Bags", bags)), "hamali_payer": "Yes", "hamali_rate": 3, "vehicle_ownership": "Owned Vehicle"}
	base.update(values)
	return FakeDoc(base)


def transport(**values):
	base = dict(vehicle_ownership="Transport Vehicle", transporter="Fast Roadways", vehicle_number="cg04 ab1234".replace(" ", ""),
		driver="DRV-1", freight_charges=5000)
	base.update(values)
	return doc(**base)


def run(document, is_transporter=1):
	original = frappe.db.get_value

	def get_value(doctype, *args, **kwargs):
		# only the Supplier lookup is faked; other lookups (such as number rounding) run as usual
		return is_transporter if doctype == "Supplier" else original(doctype, *args, **kwargs)

	with patch.object(frappe.db, "get_value", side_effect=get_value):
		po.validate_purchase_order(document)
	return document


class TestHamali(unittest.TestCase):
	def test_total_hamali_is_bags_times_rate(self):
		self.assertEqual(run(doc(bags=100, hamali_rate=3)).total_hamali, 300)
		self.assertEqual(run(doc(bags=250, hamali_rate=3.5)).total_hamali, 875)

	def test_an_edited_rate_is_used(self):
		self.assertEqual(run(doc(bags=100, hamali_rate=5)).total_hamali, 500)

	def test_no_bags_or_no_rate_gives_zero(self):
		self.assertEqual(run(doc(bags=0)).total_hamali, 0)
		self.assertEqual(run(doc(bags=None, hamali_rate=None)).total_hamali, 0)
		self.assertEqual(run(doc(bags=100, hamali_rate=0)).total_hamali, 0)

	def test_a_hand_typed_total_is_replaced_by_the_calculation(self):
		self.assertEqual(run(doc(bags=10, hamali_rate=3, total_hamali=999)).total_hamali, 30)

	def test_the_helper_rounds_to_the_given_precision(self):
		self.assertEqual(po.total_hamali(3, 3.3333, 2), 10.0)

	def test_only_items_with_uom_bags_are_counted(self):
		d = run(doc(items=rows(("Bags", 40), ("Quintal", 500), ("Trip", 3), ("Bags", 60)), hamali_rate=3))
		self.assertEqual(po.hamali_bags(d["items"]), 100)
		self.assertEqual(d.total_hamali, 300)

	def test_bags_rows_are_counted_like_nos(self):
		self.assertEqual(po.hamali_bags(rows(("Bags", 40), ("Quintal", 500), ("Nos", 60))), 100)

	def test_new_rows_may_only_use_bags_trip_or_quintal(self):
		for uom in ("Bags", "Trip", "Quintal"):
			run(doc(items=rows((uom, 1))))
		with self.assertRaises(frappe.ValidationError):
			run(doc(items=rows(("Kg", 1))))

	def test_hamali_paying_no_or_empty_gives_no_rate_and_no_total(self):
		d = run(doc(bags=100, hamali_rate=3, total_hamali=999, hamali_payer="No"))
		self.assertEqual((d.hamali_rate, d.total_hamali), (0, 0))
		for paying in (None, ""):  # a Bags row needs the answer
			with self.assertRaises(frappe.ValidationError):
				run(doc(bags=100, hamali_rate=3, hamali_payer=paying))
		self.assertEqual(run(doc(bags=100, hamali_rate=3, hamali_payer="Yes")).total_hamali, 300)

	def test_without_a_bags_row_the_hamali_answer_is_cleared_and_not_required(self):
		for paying in ("Yes", "No", None):
			d = run(doc(items=rows(("Trip", 2), ("Quintal", 5)), hamali_rate=3, total_hamali=99, hamali_payer=paying))
			self.assertEqual((d.hamali_payer, d.hamali_rate, d.total_hamali), ("", 0, 0))

	def test_no_nos_rows_gives_no_hamali(self):
		self.assertEqual(run(doc(items=rows(("Quintal", 500)))).total_hamali, 0)
		self.assertEqual(run(doc(items=[])).total_hamali, 0)
		self.assertEqual(run(doc(items=None)).total_hamali, 0)

	def test_the_uom_must_be_exactly_nos(self):
		self.assertEqual(po.hamali_bags(rows(("nos", 5), ("Nos ", 5), ("Bag", 5))), 0)

	def test_decimal_quantities_are_added(self):
		self.assertEqual(po.hamali_bags(rows(("Nos", 10.5), ("Nos", 4.5))), 15)


class TestConditions(unittest.TestCase):
	def test_qtl_bags_and_trips_are_no_longer_fields(self):
		defined = fields()
		for name in ("qtl", "bags", "trips"):
			self.assertNotIn(name, defined)

	def test_negative_hamali_rate_and_freight_are_refused(self):
		for field in ("hamali_rate",):
			with self.assertRaises(frappe.ValidationError, msg=field):
				run(doc(**{field: -1}))
		with self.assertRaises(frappe.ValidationError):
			run(transport(freight_charges=-5))

	def test_an_x_location_delivery_needs_a_location_name(self):
		for empty in (None, "", "  "):
			with self.assertRaises(frappe.ValidationError, msg=repr(empty)):
				run(doc(delivery_type="X-location", location_name=empty))

	def test_the_location_name_is_kept_and_tidied_for_an_x_location_delivery(self):
		self.assertEqual(run(doc(delivery_type="X-location", location_name="  Mandi Gate 2 ")).location_name, "Mandi Gate 2")

	def test_a_delivery_needs_no_location_name_and_clears_an_old_one(self):
		self.assertIsNone(run(doc(delivery_type="Delivery", location_name="Old Place")).location_name)
		self.assertIsNone(run(doc(delivery_type=None, location_name="Old Place")).location_name)

	def test_gunny_and_dust_are_not_forced_to_any_value(self):
		run(doc(gunny_condition=None, dust_condition=None))
		run(doc(gunny_condition="Gunny Cut", dust_condition="Yes", items=[{"item_code": "PADDY", "uom": "Bags", "qty": 1, "rate": 100}]))

	def test_the_vehicle_section_is_hidden_from_the_user(self):
		self.assertEqual(fields()["vehicle_section"]["hidden"], 1)  # the fields inside are kept, only not shown

	def test_gunny_is_cleared_while_a_row_is_a_trip(self):
		paddy = lambda *pairs: [dict(r, item_code="PADDY") for r in rows(*pairs)]
		self.assertEqual(run(doc(gunny_condition="Gunny Cut", items=paddy(("Trip", 1), ("Bags", 1)))).gunny_condition, "")
		self.assertEqual(run(doc(gunny_condition="Gunny Cut", items=paddy(("Bags", 1)))).gunny_condition, "Gunny Cut")

	def test_gunny_is_kept_only_for_boiled_rice_raw_rice_muri_rice_and_paddy(self):
		def with_item(item, quality=""):
			return run(doc(gunny_condition="Gunny Gross", items=[{"item_code": item, "uom": "Bags", "qty": 1, "rate": 100, "quality": quality}])).gunny_condition

		self.assertEqual(with_item("PADDY"), "Gunny Gross")
		self.assertEqual(with_item("BOILED-RICE", "Fresh Milling"), "Gunny Gross")
		self.assertEqual(with_item("RAW-RICE", "25% Broken Fresh Milling"), "Gunny Gross")
		self.assertEqual(with_item("MURI-RICE"), "Gunny Gross")
		for other in ("HUSK", "ASH"):
			self.assertEqual(with_item(other), "", other)
		mixed = [{"item_code": "HUSK", "uom": "Bags", "qty": 1, "rate": 100}, {"item_code": "PADDY", "uom": "Bags", "qty": 1, "rate": 100}]
		self.assertEqual(run(doc(gunny_condition="Gunny Cut", items=mixed)).gunny_condition, "Gunny Cut")  # one of the four is enough
		self.assertEqual(po.GUNNY_ITEMS, ("BOILED-RICE", "RAW-RICE", "MURI-RICE", "PADDY"))
		for name in ("purchase_order_mill.js", "purchase_receipt_mill.js"):
			self.assertIn('const GUNNY_ITEMS = ["BOILED-RICE", "RAW-RICE", "MURI-RICE", "PADDY"];', (ROOT / "public" / "js" / name).read_text(), name)

	def test_dust_is_kept_only_when_an_item_is_paddy(self):
		paddy = [{"item_code": "PADDY", "uom": "Bags", "qty": 1, "rate": 100}, {"item_code": "HUSK", "uom": "Bags", "qty": 1, "rate": 100}]
		self.assertEqual(run(doc(dust_condition="Yes", items=paddy)).dust_condition, "Yes")
		husk = [{"item_code": "HUSK", "uom": "Bags", "qty": 1, "rate": 100}]
		self.assertEqual(run(doc(dust_condition="Yes", items=husk)).dust_condition, "")


class TestTransportDetailsSwitchedOff(unittest.TestCase):
	def test_only_the_ownership_is_asked_for_now(self):
		self.assertFalse(po.ASK_TRANSPORT_DETAILS)

	def test_a_transport_vehicle_order_needs_no_other_details(self):
		d = run(doc(vehicle_ownership="Transport Vehicle"))
		self.assertEqual(d.vehicle_ownership, "Transport Vehicle")

	def test_an_owned_vehicle_order_needs_no_other_details(self):
		run(doc(vehicle_ownership="Owned Vehicle"))

	def test_hamali_is_still_calculated_for_a_transport_vehicle(self):
		self.assertEqual(run(doc(bags=40, vehicle_ownership="Transport Vehicle")).total_hamali, 120)

	def test_the_transport_fields_are_hidden_and_not_required(self):
		defined = fields()
		for name in ("transporter", "vehicle_number", "driver", "freight_charges"):
			self.assertEqual(defined[name].get("hidden"), 1, name)
			self.assertNotIn("depends_on", defined[name])
			self.assertNotIn("mandatory_depends_on", defined[name])
		self.assertNotIn("hidden", defined["vehicle_ownership"])


class TestTransportFields(unittest.TestCase):
	"""The checks of the transport details, which are switched off for now (ASK_TRANSPORT_DETAILS); the switch is turned on here."""

	def setUp(self):
		patcher = patch.object(po, "ASK_TRANSPORT_DETAILS", True)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_a_complete_transport_vehicle_order_passes_and_the_vehicle_number_is_tidied(self):
		d = run(transport(vehicle_number=" cg04ab1234 "))
		self.assertEqual(d.vehicle_number, "CG04AB1234")
		self.assertEqual((d.transporter, d.driver, d.freight_charges), ("Fast Roadways", "DRV-1", 5000))

	def test_each_missing_transport_field_is_refused(self):
		for field in ("transporter", "vehicle_number", "driver"):
			for empty in (None, "", "  "):
				with self.assertRaises(frappe.ValidationError, msg=f"{field}={empty!r}"):
					run(transport(**{field: empty}))

	def test_freight_charges_must_be_entered(self):
		for value in (None, 0):
			with self.assertRaises(frappe.ValidationError):
				run(transport(freight_charges=value))

	def test_a_supplier_that_is_not_a_transporter_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			run(transport(), is_transporter=0)

	def test_an_owned_vehicle_needs_no_transport_details(self):
		d = run(doc(vehicle_ownership="Owned Vehicle"))
		self.assertIsNone(d.transporter)

	def test_no_vehicle_ownership_needs_no_transport_details(self):
		run(doc(vehicle_ownership=None))

	def test_old_transport_details_are_cleared_when_the_vehicle_becomes_owned(self):
		d = run(transport(vehicle_ownership="Owned Vehicle"))
		self.assertEqual((d.transporter, d.vehicle_number, d.driver, d.freight_charges), (None, None, None, 0))

	def test_hamali_is_still_calculated_for_a_transport_order(self):
		self.assertEqual(run(transport(bags=40)).total_hamali, 120)


def fields():
	return {d["fieldname"]: d for d in json.loads(FIXTURE.read_text()) if d["dt"] == "Purchase Order"}


class TestFieldDefinitions(unittest.TestCase):
	def test_the_approved_fields_exist_with_the_right_types(self):
		expected = {
			"gunny_condition": "Select", "dust_condition": "Select", "location_name": "Data",
			"hamali_rate": "Currency", "hamali_payer": "Select", "total_hamali": "Currency", "delivery_type": "Select",
			"vehicle_ownership": "Select", "transporter": "Link", "vehicle_number": "Data", "driver": "Link",
			"freight_charges": "Currency", "payment_mode": "Select",
		}
		defined = fields()
		for name, fieldtype in expected.items():
			self.assertEqual(defined[name]["fieldtype"], fieldtype, name)

	def test_select_options_are_exactly_the_approved_ones(self):
		defined = fields()
		options = lambda n: [o for o in defined[n]["options"].split("\n") if o]
		self.assertEqual(options("gunny_condition"), ["Gunny Cut", "Gunny Gross"])
		self.assertEqual(options("dust_condition"), ["Yes", "No"])
		self.assertEqual(options("hamali_payer"), ["Yes", "No"])
		self.assertEqual(options("delivery_type"), ["Delivery", "X-location"])
		self.assertEqual(options("vehicle_ownership"), ["Owned Vehicle", "Transport Vehicle"])
		self.assertEqual(options("payment_mode"), ["Cash", "Bank", "50% Cash & 50% Bank"])

	def test_labels_are_the_approved_short_names(self):
		defined = fields()
		self.assertEqual(defined["mill_details_section"]["label"], "Conditions")
		self.assertEqual(defined["gunny_condition"]["label"], "Gunny")
		self.assertEqual(defined["dust_condition"]["label"], "Dust")

	def test_the_location_name_shows_and_is_required_only_for_x_location(self):
		rule = "eval:doc.delivery_type=='X-location'"
		self.assertEqual(fields()["location_name"]["depends_on"], rule)
		self.assertEqual(fields()["location_name"]["mandatory_depends_on"], rule)

	def test_the_removal_patch_is_registered_and_names_only_the_three_fields(self):
		from ivri_od.patches.v1_0 import purchase_order_remove_qty_fields as patch

		self.assertEqual(patch.FIELDS, ["Purchase Order-qtl", "Purchase Order-bags", "Purchase Order-trips"])
		self.assertIn("ivri_od.patches.v1_0.purchase_order_remove_qty_fields", (ROOT / "patches.txt").read_text().splitlines())

	def test_hamali_paying_is_a_yes_no_field_that_switches_the_rate_and_total_on(self):
		defined = fields()
		self.assertEqual(defined["hamali_payer"]["label"], "Hamali Paying")
		self.assertNotIn("default", defined["hamali_payer"])  # nothing is chosen for the user
		self.assertNotIn("reqd", defined["hamali_payer"])  # required only while a Bags row exists
		self.assertEqual(defined["hamali_payer"]["mandatory_depends_on"], "eval:(doc.items || []).some((row) => ['Bags', 'Nos'].includes(row.uom))")
		self.assertEqual(defined["hamali_section"]["hidden"], 1)  # shown by the form script while a Bags row exists
		for name in ("hamali_rate", "total_hamali"):
			self.assertEqual(defined[name]["depends_on"], "eval:doc.hamali_payer=='Yes'")
		self.assertNotIn("depends_on", defined["hamali_payer"])

	def test_hamali_rate_defaults_to_three_and_the_total_is_read_only(self):
		defined = fields()
		self.assertEqual(defined["hamali_rate"]["default"], "3")
		self.assertEqual(defined["total_hamali"]["read_only"], 1)
		self.assertNotIn("read_only", defined["hamali_rate"])

	def test_standard_fields_are_reused_not_duplicated(self):
		defined = fields()
		for standard in ("supplier", "items", "item_code", "payment_terms_template", "payment_schedule"):
			self.assertNotIn(standard, defined)
		self.assertEqual(defined["transporter"]["options"], "Supplier")
		self.assertEqual(defined["driver"]["options"], "Driver")

	def test_no_field_name_clashes_with_a_standard_purchase_order_field(self):
		standard = json.loads((Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "buying" / "doctype" / "purchase_order" / "purchase_order.json").read_text())
		standard_names = {f["fieldname"] for f in standard["fields"]}
		self.assertFalse(standard_names & set(fields()))

	def test_every_field_is_in_the_fixture_filter_and_has_the_standard_name(self):
		hooks = HOOKS.read_text()
		for name, d in fields().items():
			self.assertEqual(d["name"], f"Purchase Order-{name}")
			self.assertIn(f'"{d["name"]}"', hooks)

	def test_hooks_wire_the_validation_and_the_script(self):
		hooks = HOOKS.read_text()
		self.assertIn("ivri_od.procurement.purchase_order_mill.validate_purchase_order", hooks)
		self.assertIn('"Purchase Order": "public/js/purchase_order_mill.js"', hooks)

	def test_erpnext_itself_is_not_modified(self):
		erpnext_json = (Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "buying" / "doctype" / "purchase_order" / "purchase_order.json").read_text()
		for name in ("hamali", "vehicle_ownership", "gunny_condition"):
			self.assertNotIn(name, erpnext_json)


PROPERTY_SETTER = ROOT / "fixtures" / "property_setter.json"


class TestFormOrder(unittest.TestCase):
	"""Series section, Items, Mill Purchase Details, Vehicle, Hamali, then the rest."""

	@classmethod
	def setUpClass(cls):
		rows = [d for d in json.loads(PROPERTY_SETTER.read_text()) if d["doc_type"] == "Purchase Order" and d["property"] == "field_order"]
		cls.rows = rows
		cls.order = json.loads(rows[0]["value"])

	def test_there_is_one_field_order_for_the_purchase_order_and_it_is_in_the_fixture_filter(self):
		self.assertEqual(len(self.rows), 1)
		self.assertEqual(self.rows[0]["name"], "Purchase Order-main-field_order")
		self.assertIn('"Purchase Order-main-field_order"', HOOKS.read_text())

	def test_the_sections_follow_the_requested_order(self):
		o = self.order
		sequence = ["supplier_section", "before_items_section", "items_section", "mill_details_section", "vehicle_section", "hamali_section"]
		positions = [o.index(name) for name in sequence]
		self.assertEqual(positions, sorted(positions))
		self.assertEqual(o[0], "supplier_section")

	def test_the_series_section_is_unchanged_and_first(self):
		standard = json.loads((Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "buying" / "doctype" / "purchase_order" / "purchase_order.json").read_text())["field_order"]
		series = standard[: standard.index("accounting_dimensions_section")]
		self.assertEqual([f for f in self.order if f != "print_company_name"][: len(series)], series)  # our Print Company Name check sits right below Company

	def test_items_come_right_after_the_series_section(self):
		o = self.order
		series_end = o.index("before_items_section")
		self.assertEqual(o[series_end - 1], "supplier_warehouse")
		self.assertLess(o.index("items"), o.index("mill_details_section"))

	def test_every_standard_and_new_field_is_still_listed_once(self):
		standard = json.loads((Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "buying" / "doctype" / "purchase_order" / "purchase_order.json").read_text())
		expected = {f["fieldname"] for f in standard["fields"]} | set(fields())
		self.assertEqual(set(self.order), expected)
		self.assertEqual(len(self.order), len(set(self.order)))

	def test_the_new_sections_hold_their_own_fields_in_order(self):
		o = self.order
		def chunk(start, end):
			return o[o.index(start) + 1 : o.index(end)]
		self.assertEqual(chunk("mill_details_section", "vehicle_section"), ["gunny_condition", "dust_condition", "payment_mode", "mill_details_col", "delivery_type", "location_name"])
		self.assertEqual(chunk("vehicle_section", "discount_section"), ["vehicle_ownership", "transporter", "vehicle_number", "vehicle_col", "driver", "freight_charges"])
		self.assertEqual(chunk("discount_section", "hamali_section"), ["apply_discount_on", "base_discount_amount", "column_break_45", "additional_discount_percentage", "discount_amount"])
		self.assertEqual(chunk("hamali_section", "accounting_dimensions_section"), ["hamali_payer", "hamali_rate", "hamali_col", "total_hamali"])


def _node():
	found = shutil.which("node")
	if found:
		return found
	matches = sorted(glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/node")))
	return matches[-1] if matches else None


HARNESS = r"""
const fs = require("fs");
let h, hi;
const frappe = { ui: { form: { on(dt, handlers) { if (dt === "Purchase Order") h = handlers; else hi = handlers; } } } };
global.flt = (v) => parseFloat(v) || 0;
global.precision = () => 2;
new Function("frappe", "flt", fs.readFileSync(process.argv.slice(-1)[0], "utf8"))(frappe, global.flt);
const make = (doc) => ({ doc, values: {}, queries: {}, set_value(k, v) { this.values[k] = v; this.doc[k] = v; }, set_query(k, f) { this.queries[k] = f; }, toggle_display() {} });
const out = {};
const items = [{ uom: "Nos", qty: 40 }, { uom: "Quintal", qty: 500 }, { uom: "Nos", qty: 60 }];
let frm = make({ items, hamali_payer: "Yes", hamali_rate: 3 });
h.setup(frm); out.transporter_filter = frm.queries.transporter();
hi.qty(frm); out.hamali = frm.values.total_hamali;
frm.doc.hamali_rate = 4.5; h.hamali_rate(frm); out.hamali_after_rate = frm.values.total_hamali;
frm.doc.items = [{ uom: "Quintal", qty: 9 }]; hi.uom(frm); out.hamali_no_nos = frm.values.total_hamali;
frm.doc.items = [{ uom: "Nos", qty: 10 }]; frm.doc.hamali_payer = "Yes"; frm.doc.hamali_rate = 4.5; hi.items_remove(frm); out.hamali_after_remove = frm.values.total_hamali;
frm = make({ items, hamali_payer: "No", hamali_rate: 3 }); hi.qty(frm); out.hamali_when_no = frm.values.total_hamali;
frm = make({ items, hamali_payer: "Yes" }); h.hamali_payer(frm); out.yes_sets_rate = [frm.values.hamali_rate, frm.values.total_hamali];
frm = make({ items, hamali_payer: "Yes", hamali_rate: 5 }); h.hamali_payer(frm); out.yes_keeps_rate = [frm.values.hamali_rate, frm.values.total_hamali];
frm = make({ items, hamali_payer: "No", hamali_rate: 5 }); h.hamali_payer(frm); out.no_clears = [frm.values.hamali_rate, frm.values.total_hamali];
frm = make({ items, hamali_payer: "Yes", hamali_rate: 3, total: 10000, total_hamali: 300 }); frm.cscript = { calculate_taxes_and_totals: async () => { frm.doc.total = 20000; } }; h.setup(frm);
const erpnext_frm = frm;
const pending = frm.cscript.calculate_taxes_and_totals().then(() => { out.final_after_erpnext_total = erpnext_frm.values.total_final_amount; });
frm = make({ items, hamali_payer: "Yes", hamali_rate: 3, vehicle_ownership: "Owned Vehicle" });
h.vehicle_ownership(frm); out.cleared = Object.keys(frm.values).sort();
frm = make({ vehicle_ownership: "Transport Vehicle", transporter: "T" });
h.vehicle_ownership(frm); out.kept_for_transport = Object.keys(frm.values).length;
frm = make({ delivery_type: "Delivery" }); h.delivery_type(frm); out.location_cleared = JSON.stringify(frm.values);
frm = make({ delivery_type: "X-location" }); h.delivery_type(frm); out.location_kept = Object.keys(frm.values).length;
pending.then(() => console.log(JSON.stringify(out)));
"""


@unittest.skipUnless(_node(), "Node is not installed")
class TestFormScript(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		out = subprocess.run([_node(), "-e", HARNESS, str(JS)], capture_output=True, text=True, check=True)
		cls.r = json.loads(out.stdout)

	def test_only_transporters_are_listed(self):
		self.assertEqual(self.r["transporter_filter"], {"filters": {"is_transporter": 1}})

	def test_total_hamali_follows_the_nos_rows_and_rate_while_typing(self):
		self.assertEqual(self.r["hamali"], 300)
		self.assertEqual(self.r["hamali_after_rate"], 450)
		self.assertEqual(self.r["hamali_no_nos"], 0)
		self.assertEqual(self.r["hamali_after_remove"], 45)

	def test_hamali_is_worked_out_only_when_hamali_paying_is_yes(self):
		self.assertEqual(self.r["hamali_when_no"], 0)
		self.assertEqual(self.r["yes_sets_rate"], [3, 300])
		self.assertEqual(self.r["yes_keeps_rate"], [None, 500])  # the rate is left alone (not set again)
		self.assertEqual(self.r["no_clears"], [0, 0])

	def test_total_final_amount_follows_the_erpnext_total(self):
		self.assertEqual(self.r["final_after_erpnext_total"], 19700)  # ERPNext changed the total to 20000

	def test_choosing_an_owned_vehicle_clears_the_transport_fields(self):
		self.assertEqual(self.r["cleared"], ["driver", "freight_charges", "transporter", "vehicle_number"])

	def test_choosing_a_transport_vehicle_clears_nothing(self):
		self.assertEqual(self.r["kept_for_transport"], 0)

	def test_the_location_name_is_cleared_unless_the_delivery_is_x_location(self):
		self.assertEqual(self.r["location_cleared"], '{"location_name":""}')
		self.assertEqual(self.r["location_kept"], 0)


def item_fields():
	return {d["fieldname"]: d for d in json.loads(FIXTURE.read_text()) if d["dt"] == "Purchase Order Item"}


def js_rules():
	"""ITEM_RULES as written in the form script (strict JSON)."""
	text = JS.read_text()
	start = text.index("const ITEM_RULES = ") + len("const ITEM_RULES = ")
	return json.loads(text[start : text.index(";\nconst DEFAULT_DIMENSION")])


def item_rows(*specs):
	"""Items rows as (item_code, quality, dimension)."""
	return [FakeRow(idx=i + 1, item_code=c, quality=q, dimension=d, uom="Quintal", qty=1, rate=100) for i, (c, q, d) in enumerate(specs)]


class FakeRow(dict):
	def set(self, key, value):
		self[key] = value


HIDDEN_SECTIONS = ("currency_and_price_list", "taxes_section", "section_break_52", "totals", "totals_section")
HIDDEN_TOTALS = ("base_total", "base_net_total", "net_total")  # the Company Currency totals and the Net Total shown below the Items table


def property_setters():
	return {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}


class TestCostCenterFollowsCompany(unittest.TestCase):
	def _run(self, doc, centers):
		with patch.object(frappe, "get_cached_value", side_effect=lambda dt, name, field: {"Company": {"New Co": "Main - NEW"}, "Cost Center": centers}[dt][name] if dt == "Cost Center" else {"New Co": "Main - NEW"}[name]):
			po.align_cost_center_with_company(doc)

	def test_a_cost_center_of_another_company_is_replaced_in_the_header_and_every_row(self):
		d = FakeDoc(company="New Co", cost_center="Main - OLD", items=[FakeDoc(cost_center="Main - OLD"), FakeDoc(cost_center="Main - NEW"), FakeDoc(cost_center=None)])
		self._run(d, {"Main - OLD": "Old Co", "Main - NEW": "New Co"})
		self.assertEqual((d.cost_center, [r.cost_center for r in d["items"]]), ("Main - NEW", ["Main - NEW", "Main - NEW", None]))

	def test_a_cost_center_of_the_same_company_is_kept(self):
		d = FakeDoc(company="New Co", cost_center="Main - OTHER", items=[])
		self._run(d, {"Main - OTHER": "New Co"})
		self.assertEqual(d.cost_center, "Main - OTHER")

	def test_it_is_wired_in_before_validate_after_the_default_company(self):
		hooks = HOOKS.read_text()
		self.assertLess(hooks.index("purchase_order_mill.set_default_company"), hooks.index("purchase_order_mill.align_cost_center_with_company"))


class TestOptionalCompanyAndMandatoryItemFields(unittest.TestCase):
	def test_company_is_not_mandatory_on_the_form(self):
		setter = property_setters()["Purchase Order-company-reqd"]
		self.assertEqual((setter["doc_type"], setter["field_name"], setter["property"], setter["value"]), ("Purchase Order", "company", "reqd", "0"))

	def test_print_company_name_is_a_ticked_check_right_below_company_and_in_the_fixtures(self):
		field = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text())}["Purchase Order-print_company_name"]
		self.assertEqual((field["fieldtype"], field["insert_after"], field["default"]), ("Check", "company", "1"))
		order = json.loads(property_setters()["Purchase Order-main-field_order"]["value"])
		self.assertEqual(order.index("print_company_name"), order.index("company") + 1)
		self.assertIn("Purchase Order-print_company_name", HOOKS.read_text())

	def test_the_print_guards_company_name_logo_and_signature_line_with_the_print_flag(self):
		html = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Purchase Order - Shyamji"]["html"]
		self.assertIn("doc.print_company_name", html)
		self.assertEqual(html.count("if show_company"), 2)  # the header block and the "for <company>" signature line
		header = html[html.index("{%- if show_company %}"): html.index("{%- else %}")]
		for needle in ("shyamji_group_logo.jpg", "{{ doc.company }}", "Shyamji Group</div>"):
			self.assertIn(needle, header)

	def test_set_target_warehouse_is_hidden_on_the_form(self):
		setter = property_setters()["Purchase Order-set_warehouse-hidden"]
		self.assertEqual((setter["doc_type"], setter["field_name"], setter["property"], setter["value"]), ("Purchase Order", "set_warehouse", "hidden", "1"))

	def test_supplier_is_not_mandatory_on_the_form(self):
		setter = property_setters()["Purchase Order-supplier-reqd"]
		self.assertEqual((setter["doc_type"], setter["field_name"], setter["property"], setter["value"]), ("Purchase Order", "supplier", "reqd", "0"))

	def test_an_empty_company_becomes_the_default_company_before_saving(self):
		for empty in (None, ""):
			d = FakeDoc(company=empty)
			with patch.object(frappe.db, "exists", return_value=True):
				po.set_default_company(d)
			self.assertEqual(d.company, po.DEFAULT_COMPANY)

	def test_a_chosen_company_is_kept(self):
		d = FakeDoc(company="Other Company")
		po.set_default_company(d)
		self.assertEqual(d.company, "Other Company")

	def test_the_global_default_is_used_when_the_default_company_does_not_exist(self):
		d = FakeDoc(company=None)
		with patch.object(frappe.db, "exists", return_value=False), patch.object(frappe.defaults, "get_global_default", return_value="Site Company"):
			po.set_default_company(d)
		self.assertEqual(d.company, "Site Company")

	def test_the_hook_runs_before_validation(self):
		self.assertIn('"ivri_od.procurement.purchase_order_mill.set_default_company"', HOOKS.read_text())

	def test_every_field_of_the_items_table_is_mandatory(self):
		setters, f = property_setters(), item_fields()
		self.assertEqual(setters["Purchase Order Item-rate-reqd"]["value"], "0")  # mandatory through the next setter, except for a PDS Quality
		rule = setters["Purchase Order Item-rate-mandatory_depends_on"]
		self.assertEqual((rule["field_name"], rule["property"], rule["value"]), ("rate", "mandatory_depends_on", 'eval:doc.item_code!=\'RICE-BRAN\' && !(doc.quality || "").includes("PDS")'))
		self.assertIn("Purchase Order Item-rate-mandatory_depends_on", HOOKS.read_text())
		for name in ("quality", "dimension"):  # mandatory exactly when they are shown
			self.assertEqual(f[name]["mandatory_depends_on"], f[name]["depends_on"], name)
		standard = json.loads((Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "buying" / "doctype" / "purchase_order_item" / "purchase_order_item.json").read_text())
		reqd = {x["fieldname"] for x in standard["fields"] if x.get("reqd")}
		self.assertLessEqual({"item_code", "qty", "uom"}, reqd)  # already mandatory in ERPNext


class TestFinalAmount(unittest.TestCase):
	"""Total Final Amount = Total (INR) - Total Hamali."""

	def test_the_amount_is_total_minus_hamali(self):
		d = run(doc(bags=100, hamali_rate=3, total=10000))
		self.assertEqual((d.total_hamali, d.total_final_amount), (300, 9700))

	def test_without_hamali_the_amount_is_the_total(self):
		d = run(doc(bags=100, hamali_payer="No", total=10000))
		self.assertEqual((d.total_hamali, d.total_final_amount), (0, 10000))

	def test_an_empty_order_is_zero(self):
		self.assertEqual(run(doc(bags=0)).total_final_amount, 0)

	def test_the_helper_rounds_to_the_given_precision(self):
		self.assertEqual(po.total_final_amount(100.005, 0.004, 0, 2), 100.0)

	def test_the_additional_discount_amount_is_deducted(self):
		self.assertEqual(po.total_final_amount(10000, 300, 500), 9200)
		self.assertEqual(po.total_final_amount(10000, 0, 0), 10000)

	def test_the_fields_are_defined_as_asked(self):
		defined = fields()
		self.assertNotIn("advance_amount", defined)  # the Advance Paid field was removed
		self.assertEqual((defined["total_final_amount"]["label"], defined["total_final_amount"]["read_only"]), ("Grand Total", 1))
		self.assertEqual((defined["final_amount_section"]["fieldtype"], defined["final_amount_section"]["label"]), ("Section Break", "Final Bill Amount"))

	def test_the_company_currency_advance_field_is_hidden(self):
		setters = {d["field_name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text()) if d.get("property") == "hidden" and d["doc_type"] == "Purchase Order"}
		self.assertEqual(setters["advance_paid"]["value"], "1")
		self.assertIn("Purchase Order-advance_paid-hidden", HOOKS.read_text())

	def test_the_final_bill_amount_and_the_additional_discount_sections_are_swapped(self):
		order = json.loads(next(d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text()) if d["name"] == "Purchase Order-main-field_order")["value"])
		# the Final Bill Amount section sits where the Additional Discount section was (right after Advance Paid) ...
		self.assertEqual(order[order.index("advance_paid") + 1 : order.index("advance_paid") + 3], ["final_amount_section", "total_final_amount"])
		# ... and the Additional Discount section sits where the Final Bill Amount was (right after Freight Charges, before Hamali)
		self.assertEqual(order[order.index("freight_charges") + 1], "discount_section")
		self.assertEqual(order[order.index("discount_amount") + 1], "hamali_section")
		self.assertEqual(fields()["final_amount_section"]["insert_after"], "advance_paid")


class TestPaymentMode(unittest.TestCase):
	def test_payment_mode_is_in_the_details_tab_under_dust_in_conditions(self):
		order = json.loads(next(d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text()) if d["name"] == "Purchase Order-main-field_order")["value"])
		self.assertEqual(order[order.index("dust_condition") + 1], "payment_mode")
		self.assertLess(order.index("payment_mode"), order.index("terms_tab"))
		self.assertEqual(fields()["payment_mode"]["insert_after"], "dust_condition")
		self.assertEqual(fields()["payment_mode"]["options"], "\nCash\nBank\n50% Cash & 50% Bank")


class TestHiddenSections(unittest.TestCase):
	"""Currency and Price List, Taxes and Charges (with its table and totals), Totals and Additional Discount are hidden from users."""

	def test_each_section_is_hidden_by_a_property_setter(self):
		setters = {d["field_name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text()) if d.get("property") == "hidden" and d["doc_type"] == "Purchase Order" and d["field_name"] not in ("advance_paid", "set_warehouse", "scan_barcode") and d["value"] == "1"}
		self.assertEqual(set(setters), set(HIDDEN_SECTIONS) | set(HIDDEN_TOTALS))
		for name in HIDDEN_SECTIONS + HIDDEN_TOTALS:
			self.assertEqual((setters[name]["value"], setters[name]["doctype_or_field"]), ("1", "DocField"), name)
			self.assertIn(setters[name]["name"], HOOKS.read_text())

	def test_only_sections_are_hidden_not_other_fields(self):
		standard = json.loads((Path(frappe.__file__).resolve().parents[2] / "erpnext" / "erpnext" / "buying" / "doctype" / "purchase_order" / "purchase_order.json").read_text())
		types = {f["fieldname"]: f["fieldtype"] for f in standard["fields"]}
		for name in HIDDEN_SECTIONS:
			self.assertEqual(types[name], "Section Break", name)


class TestTotalsStayHiddenWhenErpnextToggles(unittest.TestCase):
	def test_the_form_script_turns_a_show_of_the_hidden_totals_into_a_hide(self):
		script = (ROOT / "public" / "js" / "purchase_order_mill.js").read_text()
		self.assertIn('const ALWAYS_HIDDEN_TOTALS = ["net_total", "base_net_total", "base_total"];', script)
		self.assertIn("keep_totals_hidden(frm);", script)
		self.assertEqual(script.count("keep_totals_hidden(frm);"), 2)  # setup and refresh call it


class TestRateIsRequiredUnlessPds(unittest.TestCase):
	def test_a_row_without_a_rate_is_refused_unless_its_quality_is_pds(self):
		for quality in ("Fresh Milling", "", None, "Lot Delivery"):
			for rate in (0, None, -1):
				with self.assertRaises(frappe.ValidationError, msg=(quality, rate)):
					po.validate_item_rate(FakeDoc(items=[FakeDoc(idx=1, quality=quality, rate=rate)]))

	def test_pds_qualities_and_rows_with_a_rate_pass(self):
		for quality in ("PDS", "25% Broken PDS", "10% Broken PDS"):
			po.validate_item_rate(FakeDoc(items=[FakeDoc(idx=1, quality=quality, rate=0)]))
		po.validate_item_rate(FakeDoc(items=[FakeDoc(idx=1, quality="Fresh Milling", rate=2300)]))

	def test_it_runs_in_the_purchase_order_validation(self):
		import inspect

		self.assertIn("validate_item_rate(doc)", inspect.getsource(po.validate_purchase_order))


class TestWarehouseIsNotAskedOnAPurchaseOrder(unittest.TestCase):
	def setUp(self):
		po.uninstall_no_warehouse_check()
		self.addCleanup(po.install_no_warehouse_check)
		self.addCleanup(po.uninstall_no_warehouse_check)

	def test_only_a_purchase_order_row_may_go_without_a_warehouse(self):
		from erpnext.buying import utils

		def original(row, item):
			return "checked"

		with patch.object(utils, "validate_stock_item_warehouse", new=original):
			po.install_no_warehouse_check()
			po.install_no_warehouse_check()  # twice is the same as once
			wrapped = utils.validate_stock_item_warehouse
			self.assertIsNot(wrapped, original)
			self.assertIsNone(wrapped(frappe._dict(parenttype="Purchase Order"), None))
			self.assertEqual(wrapped(frappe._dict(parenttype="Purchase Receipt"), None), "checked")
			po.uninstall_no_warehouse_check()
			self.assertIs(utils.validate_stock_item_warehouse, original)

	def test_the_warehouse_column_is_hidden_and_the_check_is_installed(self):
		setter = property_setters()["Purchase Order Item-warehouse-hidden"]
		self.assertEqual((setter["doc_type"], setter["field_name"], setter["property"], setter["value"]), ("Purchase Order Item", "warehouse", "hidden", "1"))
		hooks = HOOKS.read_text()
		self.assertIn("Purchase Order Item-warehouse-hidden", hooks)
		self.assertEqual(hooks.count("purchase_order_mill.install_no_warehouse_check"), 2)


class TestRateIsNotFilledAutomatically(unittest.TestCase):
	def setUp(self):
		po.uninstall_no_auto_rate()
		self.addCleanup(po.install_no_auto_rate)
		self.addCleanup(po.uninstall_no_auto_rate)

	def test_a_purchase_order_row_finds_no_price_and_another_document_keeps_it(self):
		from erpnext.stock import get_item_details as gid

		real = gid.get_price_list_rate

		def original(ctx, item_doc, out=None):
			return "looked up"

		with patch.object(gid, "get_price_list_rate", new=original):
			po.install_no_auto_rate()
			po.install_no_auto_rate()  # twice is the same as once
			wrapped = gid.get_price_list_rate
			self.assertNotEqual(wrapped, original)
			self.assertEqual(wrapped(frappe._dict(doctype="Purchase Order"), None), gid.ItemDetails())
			self.assertEqual(wrapped(frappe._dict(doctype="Child", parenttype="Purchase Order"), None), gid.ItemDetails())
			self.assertEqual(wrapped(frappe._dict(doctype="Sales Invoice"), None), "looked up")  # the Purchase Invoice follows the typed-in Rate rule too
			po.uninstall_no_auto_rate()
			self.assertEqual(gid.get_price_list_rate, original)
		self.assertIs(gid.get_price_list_rate, real)

	def test_it_is_installed_for_requests_and_jobs(self):
		hooks = HOOKS.read_text()
		self.assertEqual(hooks.count("purchase_order_mill.install_no_auto_rate"), 2)



	def test_the_two_fields_are_selects_on_the_item_row_right_after_the_item(self):
		f = item_fields()
		self.assertEqual((f["quality"]["fieldtype"], f["quality"]["insert_after"]), ("Select", "item_code"))
		self.assertEqual((f["dimension"]["fieldtype"], f["dimension"]["insert_after"]), ("Select", "quality"))
		for name in ("Purchase Order Item-quality", "Purchase Order Item-dimension"):
			self.assertIn(name, HOOKS.read_text())

	def test_the_fields_hold_every_choice_so_saved_values_stay_valid(self):
		f = item_fields()
		for field in ("quality", "dimension"):
			wanted = {c for rule in po.ITEM_RULES.values() for c in rule[field]}
			self.assertEqual(set(filter(None, f[field]["options"].split("\n"))), wanted)

	def test_a_field_is_hidden_unless_the_item_has_choices(self):
		f = item_fields()
		for field in ("quality", "dimension"):
			shown = {code for code, rule in po.ITEM_RULES.items() if rule[field]}
			expr = f[field]["depends_on"]
			self.assertTrue(expr.startswith("eval:") and expr.endswith(".includes(doc.item_code)"))
			self.assertEqual(set(json.loads(expr[5 : expr.index(".includes")].replace("'", '"'))), shown)

	def test_the_item_codes_are_the_real_item_codes(self):
		self.assertEqual(
			set(po.ITEM_RULES),
			{"BOILED-RICE", "BIOMASS-PELLET", "BIOMASS-BRIQUETTE", "RAW-RICE", "RICE-BRAN", "REJECTION", "HUSK", "ASH"},
		)

	def test_python_and_form_script_hold_the_same_rules(self):
		self.assertEqual(js_rules(), po.ITEM_RULES)

	def test_choices_of_the_eight_items(self):
		r = po.ITEM_RULES
		self.assertEqual(r["BOILED-RICE"], {"quality": ["Fresh Milling", "Lot Delivery", "PDS"], "dimension": []})
		self.assertEqual(r["BIOMASS-PELLET"]["dimension"], ["8mm", "10mm", "16mm"])
		self.assertEqual(r["BIOMASS-BRIQUETTE"]["quality"], ["Rice Husk", "Saw Dust", "Mix"])
		self.assertEqual(r["BIOMASS-BRIQUETTE"]["dimension"], ["90mm"])
		self.assertEqual(len(r["RAW-RICE"]["quality"]), 6)
		self.assertEqual(r["RICE-BRAN"]["quality"], ["Boiled", "Raw", "Muri", "Silky"])
		self.assertEqual(r["REJECTION"]["quality"], ["Boiled", "Raw", "Muri"])
		for code in ("HUSK", "ASH"):
			self.assertEqual(r[code], {"quality": [], "dimension": []})

	def test_valid_choices_are_accepted_for_every_item(self):
		for code, rule in po.ITEM_RULES.items():
			for quality in rule["quality"] or [None]:
				for dimension in rule["dimension"] or [None]:
					d = doc(items=item_rows((code, quality, dimension)))
					run(d)
					self.assertEqual((d["items"][0]["quality"], d["items"][0]["dimension"]), (quality, dimension))

	def test_a_choice_of_another_item_is_refused(self):
		for code, quality, dimension in (
			("BOILED-RICE", "Boiled", None),
			("BIOMASS-PELLET", "Rice Husk", "90mm"),
			("RICE-BRAN", "Mix", None),
			("RAW-RICE", "Fresh Milling", None),
		):
			with self.assertRaises(frappe.ValidationError):
				run(doc(items=item_rows((code, quality, dimension))))

	def test_a_row_must_have_the_quality_and_dimension_its_item_has_choices_for(self):
		for code, quality, dimension in (
			("BOILED-RICE", None, None),
			("RAW-RICE", "", None),
			("RICE-BRAN", "  ", None),
			("BIOMASS-PELLET", None, "8mm"),
			("BIOMASS-PELLET", "Mix", None),
			("BIOMASS-PELLET", "Mix", ""),
		):
			with self.assertRaises(frappe.ValidationError, msg=f"{code} {quality!r} {dimension!r}"):
				run(doc(items=item_rows((code, quality, dimension))))

	def test_an_item_without_choices_clears_old_values(self):
		for code in ("HUSK", "ASH", "PADDY", "MURI-RICE"):
			d = doc(items=item_rows((code, "Mix", "8mm")))
			run(d)
			self.assertEqual((d["items"][0]["quality"], d["items"][0]["dimension"]), (None, None))
		d = doc(items=item_rows(("BOILED-RICE", "PDS", "8mm")))
		run(d)
		self.assertEqual((d["items"][0]["quality"], d["items"][0]["dimension"]), ("PDS", None))

	def test_a_briquette_without_dimension_gets_90mm(self):
		d = doc(items=item_rows(("BIOMASS-BRIQUETTE", "Mix", None)))
		run(d)
		self.assertEqual(d["items"][0]["dimension"], "90mm")

	def test_each_row_is_checked_on_its_own(self):
		d = doc(items=item_rows(("BOILED-RICE", "PDS", None), ("BIOMASS-PELLET", "Mix", "10mm"), ("HUSK", None, None)))
		run(d)
		self.assertEqual([(r["quality"], r["dimension"]) for r in d["items"]], [("PDS", None), ("Mix", "10mm"), (None, None)])
		with self.assertRaises(frappe.ValidationError):
			run(doc(items=item_rows(("BOILED-RICE", "PDS", None), ("RICE-BRAN", "PDS", None))))


ROW_HARNESS = r"""
const fs = require("fs");
let h, hi;
const frappe = {
	ui: { form: { on(dt, handlers) { if (dt === "Purchase Order") h = handlers; else hi = handlers; } } },
	meta: { get_docfield: (dt, f, name) => (dfs[name] = dfs[name] || {})[f] = (dfs[name][f] || { options: "" }) },
	model: { set_value(cdt, cdn, f, v) { locals[cdt][cdn][f] = v; log.push([cdn, f, v]); } },
};
const dfs = {}, log = [];
global.locals = {};
global.flt = (v) => parseFloat(v) || 0;
global.precision = () => 2;
new Function("frappe", "flt", "locals", fs.readFileSync(process.argv.slice(-1)[0], "utf8"))(frappe, (v) => parseFloat(v) || 0, global.locals);
const rows = [
	{ doctype: "Purchase Order Item", name: "r1", item_code: "BOILED-RICE", quality: "PDS", dimension: "" },
	{ doctype: "Purchase Order Item", name: "r2", item_code: "BIOMASS-PELLET", quality: "Mix", dimension: "10mm" },
	{ doctype: "Purchase Order Item", name: "r3", item_code: "HUSK", quality: "", dimension: "" },
];
rows.forEach((r) => (global.locals[r.doctype] = global.locals[r.doctype] || {}, global.locals[r.doctype][r.name] = r));
const refreshed = [];
const columns = { quality: true, dimension: true }, column_calls = [];
const grid = {
	grid_rows_by_docname: new Proxy({}, { get: (_, n) => ({ refresh() { refreshed.push(n); } }) }),
	set_column_disp_in_list_view(fields, show) { fields.forEach((f) => (columns[f] = show)); column_calls.push(fields.length); },
};
const frm = { doc: { items: rows }, fields_dict: { items: { grid } }, set_query() {}, set_value() {}, toggle_display(f, show) { shown[f] = show; }, is_new() { return true; } };
const shown = {};
const out = {};
h.refresh(frm);
out.options_on_load = Object.fromEntries(Object.entries(dfs).map(([n, d]) => [n, [d.quality.options, d.dimension.options]]));
out.nothing_changed_on_load = log.length;
out.columns_on_load = { ...columns };
rows[0].item_code = "RICE-BRAN"; hi.item_code(frm, "Purchase Order Item", "r1");
out.after_change_r1 = [rows[0].quality, rows[0].dimension];
rows[2].item_code = "BIOMASS-BRIQUETTE"; hi.item_code(frm, "Purchase Order Item", "r3");
out.briquette = [rows[2].quality, rows[2].dimension, dfs.r3.dimension.options];
rows[1].item_code = "BIOMASS-BRIQUETTE"; hi.item_code(frm, "Purchase Order Item", "r2");
out.pellet_to_briquette = [rows[1].quality, rows[1].dimension];
rows[1].item_code = "ASH"; hi.item_code(frm, "Purchase Order Item", "r2");
out.to_ash = [rows[1].quality, rows[1].dimension, dfs.r2.quality.options];
hi.form_render(frm, "Purchase Order Item", "r1");
out.columns_now = { ...columns };
const calls_before = column_calls.length; hi.form_render(frm, "Purchase Order Item", "r1"); out.no_redraw_when_unchanged = column_calls.length === calls_before;
rows[2].item_code = "HUSK"; hi.item_code(frm, "Purchase Order Item", "r3");
out.only_quality = { ...columns };
rows.splice(0, 1); hi.items_remove(frm);
out.after_remove = { ...columns };
rows.length = 0; h.refresh(frm);
out.empty_table = { ...columns };
rows.push({ doctype: "Purchase Order Item", name: "r4", item_code: "HUSK", uom: "Trip" }); global.locals["Purchase Order Item"].r4 = rows[0];
hi.uom(frm, "Purchase Order Item", "r4"); out.trip_row = [{ ...columns }, rows[0].avg_wt]; out.gunny_with_trip = shown.gunny_condition;
rows[0].quality = "Lot Delivery"; hi.quality(frm, "Purchase Order Item", "r4"); out.lot_delivery = rows[0].avg_wt;
rows[0].quality = "25% Broken Lot Delivery"; hi.quality(frm, "Purchase Order Item", "r4"); out.broken_lot_delivery = rows[0].avg_wt;
rows[0].avg_wt = 27; hi.quality(frm, "Purchase Order Item", "r4"); out.typed_value_kept = rows[0].avg_wt;
rows[0].avg_wt = 29; rows[0].quality = "PDS"; hi.quality(frm, "Purchase Order Item", "r4"); out.back_to_25 = rows[0].avg_wt;
rows[0].uom = "Bags"; rows[0].avg_wt = 25; rows[0].quality = "Lot Delivery"; hi.quality(frm, "Purchase Order Item", "r4"); out.not_trip = rows[0].avg_wt;
rows[0].quality = "PDS"; hi.quality(frm, "Purchase Order Item", "r4"); out.pds_shown = ["quality_pds_rate_1", "quality_pds_rate_2", "quality_pds_rate_3"].map((f) => shown[f]);
rows[0].quality = "10% Broken PDS"; hi.quality(frm, "Purchase Order Item", "r4"); out.broken_pds_shown = shown.quality_pds_rate_1;
rows[0].quality = "Raw"; hi.quality(frm, "Purchase Order Item", "r4"); out.other_hidden = shown.quality_pds_rate_1;
out.refreshed_rows = [...new Set(refreshed)].sort();
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(_node(), "Node is not installed")
class TestRowScript(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		out = subprocess.run([_node(), "-e", ROW_HARNESS, str(JS)], capture_output=True, text=True, check=True)
		cls.r = json.loads(out.stdout)

	def test_the_trip_row_shows_the_avg_wt_column_and_fills_25(self):
		self.assertEqual([self.cols(self.r["trip_row"][0]), self.r["trip_row"][1]], [{"quality": False, "dimension": False, "avg_wt": True}, 25])

	def test_the_pds_rates_show_only_while_a_row_has_a_pds_quality(self):
		self.assertEqual(self.r["pds_shown"], [True, True, True])
		self.assertTrue(self.r["broken_pds_shown"])
		self.assertFalse(self.r["other_hidden"])

	def test_the_gunny_field_is_hidden_while_a_row_is_a_trip(self):
		self.assertFalse(self.r["gunny_with_trip"])

	def test_a_lot_delivery_trip_row_starts_with_avg_wt_29(self):
		self.assertEqual(self.r["lot_delivery"], 29)
		self.assertEqual(self.r["broken_lot_delivery"], 29)
		self.assertEqual(self.r["typed_value_kept"], 27)  # a value the user typed is not replaced
		self.assertEqual(self.r["back_to_25"], 25)  # another Quality goes back to the default
		self.assertEqual(self.r["not_trip"], 25)  # only a Trip row is touched

	def test_each_row_gets_the_choices_of_its_own_item_on_load_without_changing_values(self):
		o = self.r["options_on_load"]
		self.assertEqual(o["r1"], ["\nFresh Milling\nLot Delivery\nPDS", ""])
		self.assertEqual(o["r2"], ["\nRice Husk\nSaw Dust\nMix", "\n8mm\n10mm\n16mm"])
		self.assertEqual(o["r3"], ["", ""])
		self.assertEqual(self.r["nothing_changed_on_load"], 0)

	def test_changing_the_item_clears_a_choice_it_does_not_have(self):
		self.assertEqual(self.r["after_change_r1"], ["", ""])

	def test_a_briquette_row_defaults_to_90mm(self):
		self.assertEqual(self.r["briquette"], ["", "90mm", "\n90mm"])

	def test_a_pellet_dimension_is_replaced_when_the_item_becomes_a_briquette(self):
		self.assertEqual(self.r["pellet_to_briquette"], ["Mix", "90mm"])

	def test_an_item_without_choices_clears_both_and_offers_none(self):
		self.assertEqual(self.r["to_ash"], ["", "", ""])

	@staticmethod
	def cols(columns):
		"""The Quality, Dimension and Avg Wt columns only (the Rice Bran columns are checked in TestRiceBranFields)."""
		return {k: v for k, v in columns.items() if k in ("quality", "dimension", "avg_wt")}

	def test_a_column_shows_only_while_a_row_needs_it(self):
		self.assertEqual(self.cols(self.r["columns_on_load"]), {"quality": True, "dimension": True, "avg_wt": False})  # boiled rice and pellet rows
		self.assertEqual(self.cols(self.r["columns_now"]), {"quality": True, "dimension": True, "avg_wt": False})  # bran, ash and briquette rows: the briquette needs both
		self.assertEqual(self.cols(self.r["only_quality"]), {"quality": True, "dimension": False, "avg_wt": False})  # only the bran row is left with choices
		self.assertEqual(self.cols(self.r["after_remove"]), {"quality": False, "dimension": False, "avg_wt": False})
		self.assertEqual(self.cols(self.r["empty_table"]), {"quality": False, "dimension": False, "avg_wt": False})
		self.assertTrue(self.r["no_redraw_when_unchanged"])

	def test_every_changed_row_is_redrawn(self):
		self.assertEqual(self.r["refreshed_rows"], ["r1", "r2", "r3"])


if __name__ == "__main__":
	unittest.main()


class TestTripAvgWt(unittest.TestCase):
	"""A Trip row has an Avg Wt (25 unless changed) and its Amount is Quantity x Avg Wt(MT) x 10 x Rate (per quintal)."""

	def test_the_amount_is_quantity_times_avg_wt_times_rate(self):
		self.assertEqual(po.trip_amount(2, 25, 100), 50000)  # 2 trips x 25 MT x 10 quintal x 100 per quintal
		self.assertEqual(po.trip_amount(3, 24.5, 10.5, 2), 7717.5)

	def test_the_avg_wt_field_is_defined_as_asked(self):
		f = {d["fieldname"]: d for d in json.loads(FIXTURE.read_text()) if d["dt"] == "Purchase Order Item"}["avg_wt"]
		self.assertEqual((f["label"], f["fieldtype"], f["default"], f["insert_after"]), ("Avg Wt(MT)", "Float", "25", "uom"))
		self.assertEqual(f["depends_on"], "eval:doc.uom=='Trip'")
		self.assertEqual(f["mandatory_depends_on"], "eval:doc.uom=='Trip'")
		self.assertEqual(po.DEFAULT_AVG_WT, 25)
		self.assertIn("Purchase Order Item-avg_wt", HOOKS.read_text())

	def test_a_trip_row_needs_an_avg_wt_above_zero(self):
		run(doc(items=[{"uom": "Trip", "qty": 1, "rate": 100, "avg_wt": 25}]))
		run(doc(items=[{"uom": "Bags", "qty": 1, "rate": 100, "avg_wt": 0}]))
		for bad in (0, None, -1):
			with self.assertRaises(frappe.ValidationError):
				run(doc(items=[{"uom": "Trip", "qty": 1, "rate": 100, "avg_wt": bad}]))

	def test_erpnext_amount_step_is_wrapped_for_trip_rows_only(self):
		from erpnext.controllers import taxes_and_totals as tt

		po.uninstall_trip_amount()
		try:
			po.install_trip_amount()
			po.install_trip_amount()  # twice is the same as once
			calc = tt.calculate_taxes_and_totals
			self.assertIs(calc.calculate_item_values.__closure__ is not None, True)

			class Row(FakeDoc):
				def precision(self, fieldname):
					return 2

			trip = Row(uom="Trip", qty=2, avg_wt=25, rate=100)
			bags = Row(uom="Bags", qty=2, avg_wt=25, rate=100)
			order = types.SimpleNamespace(items=[trip, bags], conversion_rate=1, round_floats_in=lambda *a, **k: None)
			order.get = lambda key, default=None: {"doctype": "Purchase Order"}.get(key, default)
			holder = type("Holder", (), {})()
			holder.doc, holder.discount_amount_applied = order, False
			holder.calculate_item_rate = lambda item: None
			holder._set_in_company_currency = lambda item, names: [item.__setitem__("base_" + n, item.get(n)) for n in names]
			calc.calculate_item_values(holder)
			self.assertEqual((trip["amount"], trip["net_amount"], trip["base_amount"]), (50000, 50000, 50000))  # 2 x 25 MT x 10 x 100
			self.assertEqual(bags["amount"], 200)  # 2 x 100: other UOMs are left alone
		finally:
			po.uninstall_trip_amount()
			po.install_trip_amount()


class TestPdsRates(unittest.TestCase):
	"""Three Quality PDS Rate fields sit right below the Items table and are used only while a row's Quality is PDS."""

	NAMES = [("quality_pds_rate_1", "1st Quality PDS Rate"), ("quality_pds_rate_2", "2nd Quality PDS Rate"), ("quality_pds_rate_3", "3rd Quality PDS Rate")]

	def test_the_fields_are_defined_and_listed_right_after_the_items_table(self):
		for fieldname, label in self.NAMES:
			f = fields()[fieldname]
			self.assertEqual((f["label"], f["fieldtype"], f["hidden"]), (label, "Currency", 1))
			self.assertIn("Purchase Order-" + fieldname, HOOKS.read_text())
		order = json.loads(next(d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text()) if d["name"] == "Purchase Order-main-field_order")["value"])
		i = order.index("items")
		self.assertEqual(order[i + 1 : i + 4], [n for n, _ in self.NAMES])

	def test_the_rates_are_kept_only_while_a_row_has_a_pds_quality(self):
		rates = dict(quality_pds_rate_1=10, quality_pds_rate_2=20, quality_pds_rate_3=30)
		row = lambda item, quality: [FakeDoc(item_code=item, uom="Bags", qty=1, rate=100, quality=quality)]
		for items in (row("BOILED-RICE", "PDS"), row("RAW-RICE", "25% Broken PDS")):
			d = run(doc(items=items, **rates))
			self.assertEqual((d.quality_pds_rate_1, d.quality_pds_rate_2, d.quality_pds_rate_3), (10, 20, 30))
		for items in (row("RICE-BRAN", "Raw"), row("HUSK", None)):
			d = run(doc(items=items, **rates))
			self.assertEqual((d.quality_pds_rate_1, d.quality_pds_rate_2, d.quality_pds_rate_3), (0, 0, 0))


class TestLabelsAndDescriptions(unittest.TestCase):
	def test_dimension_is_labelled_in_mm(self):
		item_fields = {d["fieldname"]: d for d in json.loads(FIXTURE.read_text()) if d["dt"] == "Purchase Order Item"}
		self.assertEqual(item_fields["dimension"]["label"], "Dimension(mm)")

	def test_no_field_of_the_purchase_order_carries_a_description(self):
		for d in json.loads(FIXTURE.read_text()):
			if d["dt"] in ("Purchase Order", "Purchase Order Item"):
				self.assertEqual(d.get("description", ""), "", d["name"])


class TestItemTitle(unittest.TestCase):
	"""An Item whose name is its code written another way is shown once in the Items table ("HUSK", not "HUSK: Husk")."""

	def test_the_code_is_not_repeated_as_the_name(self):
		script = """
const fs = require("fs");
const frappe = { form: { link_formatters: { Item: (v, d) => v + ": " + d.item_name } }, ui: { form: { on() {} } } };
new Function("frappe", "flt", fs.readFileSync(process.argv.slice(-1)[0], "utf8"))(frappe, (v) => parseFloat(v) || 0);
const f = frappe.form.link_formatters.Item, row = (n) => ({ doctype: "Purchase Order Item", item_name: n });
console.log(JSON.stringify([f("HUSK", row("Husk")), f("BOILED-RICE", row("Boiled Rice")), f("MURI-RICE", row("Muri Rice")), f("PADDY", row("Paddy Special")), f("HUSK", { doctype: "Item", item_name: "Husk" })]));
"""
		out = subprocess.run([_node(), "-e", script, str(JS)], capture_output=True, text=True, check=True)
		self.assertEqual(json.loads(out.stdout), ["HUSK", "BOILED-RICE", "MURI-RICE", "PADDY: Paddy Special", "HUSK: Husk"])


class TestItemColumnWidth(unittest.TestCase):
	def test_the_item_column_is_three_wide(self):
		setters = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		s = setters["Purchase Order Item-item_code-columns"]
		self.assertEqual((s["doc_type"], s["field_name"], s["property"], s["value"]), ("Purchase Order Item", "item_code", "columns", "3"))
		self.assertIn('"Purchase Order Item-item_code-columns"', HOOKS.read_text())


class TestAdditionalDiscountForCash(unittest.TestCase):
	def test_the_section_shows_only_for_cash(self):
		setter = property_setters()["Purchase Order-discount_section-depends_on"]
		self.assertEqual((setter["field_name"], setter["property"], setter["value"]), ("discount_section", "depends_on", "eval:doc.payment_mode=='Cash'"))
		self.assertNotIn("Purchase Order-discount_section-hidden", property_setters())
		self.assertIn("Purchase Order-discount_section-depends_on", HOOKS.read_text())

	def test_an_old_discount_is_cleared_unless_the_mode_is_cash(self):
		for mode in ("Bank", "50% Cash & 50% Bank", None, ""):
			d = FakeDoc(payment_mode=mode, discount_amount=500, additional_discount_percentage=5)
			po.clear_discount_unless_cash(d)
			self.assertEqual((d.discount_amount, d.additional_discount_percentage), (0, 0), mode)
		d = FakeDoc(payment_mode="Cash", discount_amount=500, additional_discount_percentage=5)
		po.clear_discount_unless_cash(d)
		self.assertEqual((d.discount_amount, d.additional_discount_percentage), (500, 5))

