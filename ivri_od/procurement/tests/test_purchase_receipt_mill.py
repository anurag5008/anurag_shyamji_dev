# Copyright (c) 2026, Profezzo and contributors
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

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

	def get_doc_before_save(self):
		return None

	def precision(self, fieldname):
		return None  # no rounding: flt() with a precision reads System Settings through frappe.db, which these tests patch


class FakeRow(FakeDoc):
	pass


def fields():
	return {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text()) if d["dt"].startswith("Purchase Receipt")}


class TestItemStatus(unittest.TestCase):
	def test_status_counts_earlier_receipts_plus_this_one_against_the_order(self):
		self.assertEqual(pr.item_status(100, 0, 40), pr.PENDING)
		self.assertEqual(pr.item_status(100, 60, 40), pr.COMPLETE)
		self.assertEqual(pr.item_status(100, 60, 50), pr.EXCESS)
		self.assertEqual(pr.item_status(0, 0, 5), "")

	def test_the_receipt_shows_the_status_that_needs_most_attention(self):
		self.assertEqual(pr.receipt_status([pr.COMPLETE, pr.PENDING]), pr.PENDING)
		self.assertEqual(pr.receipt_status([pr.COMPLETE, pr.EXCESS, pr.PENDING]), pr.EXCESS)
		self.assertEqual(pr.receipt_status([pr.COMPLETE]), pr.COMPLETE)
		self.assertEqual(pr.receipt_status(["", None]), "")


class TestValidate(unittest.TestCase):
	def _doc(self, **values):
		base = dict(items=[FakeRow(purchase_order_item="POI-1", received_qty=40, qty=40, uom="Bags", rate=100)], total=1000, discount_amount=0, hamali_payer="Yes", hamali_rate=3)
		base.update(values)
		return FakeDoc(base)

	def _run(self, doc, line):
		with patch.object(frappe.db, "get_value", return_value=frappe._dict(line) if line else None):
			pr.validate_purchase_receipt(doc)
		return doc

	def test_rows_get_the_ordered_quantity_and_a_status_and_the_receipt_follows(self):
		d = self._run(self._doc(), {"qty": 100, "received_qty": 20})
		self.assertEqual((d["items"][0].ordered_qty, d["items"][0].receipt_status, d.receipt_status), (100, pr.PENDING, pr.PENDING))
		d = self._run(self._doc(), {"qty": 100, "received_qty": 60})
		self.assertEqual(d.receipt_status, pr.COMPLETE)

	def test_hamali_and_final_amount(self):
		d = self._run(self._doc(), {"qty": 100, "received_qty": 0})
		self.assertEqual((d.total_hamali, d.total_final_amount), (120, 880))  # 40 bags x 3
		d = self._run(self._doc(hamali_payer="No"), {"qty": 100, "received_qty": 0})
		self.assertEqual((d.hamali_rate, d.total_hamali, d.total_final_amount), (0, 0, 1000))

	def test_a_row_not_made_from_an_order_is_left_alone(self):
		doc = self._doc()
		doc["items"][0].purchase_order_item = None
		self._run(doc, None)
		self.assertEqual((doc["items"][0].ordered_qty, doc.receipt_status), (None, ""))


class TestFixtures(unittest.TestCase):
	def test_the_order_fields_carry_the_same_names_so_erpnext_copies_them(self):
		po = {d["fieldname"] for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text()) if d["dt"] in ("Purchase Order", "Purchase Order Item")}
		receipt = {d["fieldname"] for d in fields().values()}
		for name in ("quality", "dimension", "avg_wt", "gunny_condition", "dust_condition", "payment_mode", "delivery_type", "location_name", "hamali_payer", "hamali_rate", "total_hamali", "print_company_name", "vehicle_number", "driver"):
			self.assertIn(name, po, name)
			self.assertIn(name, receipt, name)

	def test_quality_and_dimension_choices_match_the_order(self):
		allf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text())}
		for name in ("quality", "dimension"):
			self.assertEqual(allf[f"Purchase Receipt Item-{name}"]["options"], allf[f"Purchase Order Item-{name}"]["options"])

	def test_every_new_field_is_in_the_fixtures_filter_and_the_hook_is_wired(self):
		hooks = HOOKS.read_text()
		for name in fields():
			self.assertIn(f'"{name}"', hooks, name)
		self.assertIn("purchase_receipt_mill.validate_purchase_receipt", hooks)
		self.assertIn('"Purchase Receipt - Shyamji"', hooks)
		self.assertIn('"Purchase Receipt-supplier-reqd"', hooks)

	def test_supplier_is_optional_and_the_print_guards_the_company_block(self):
		setter = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}["Purchase Receipt-supplier-reqd"]
		self.assertEqual((setter["doc_type"], setter["field_name"], setter["property"], setter["value"]), ("Purchase Receipt", "supplier", "reqd", "0"))
		html = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Purchase Receipt - Shyamji"]["html"]
		self.assertEqual(html.count("if show_company"), 2)


class TestSimpleForm(unittest.TestCase):
	"""The Purchase Receipt shows only what the plant staff need: the rest is hidden by Property Setters."""

	STAYS_VISIBLE = {
		"Purchase Receipt": {"purchase_order", "vehicle_ownership", "transporter", "freight_charges", "quality_pds_rate_1", "quality_pds_rate_2", "quality_pds_rate_3", "supplier", "supplier_name", "supplier_delivery_note", "posting_date", "company", "print_company_name", "set_warehouse", "items",
			"total_qty", "total", "vehicle_number", "driver", "gunny_condition", "dust_condition", "payment_mode", "delivery_type", "moisture", "dust_kg",
			"hamali_payer", "hamali_rate", "total_hamali", "receipt_status", "total_final_amount"},
		"Purchase Receipt Item": {"item_code", "quality", "dimension", "avg_wt", "ordered_qty", "qty", "uom", "rate", "amount", "warehouse", "batch_no", "purchase_order"},
	}

	def _hooks_tuple(self):
		import ast

		tree = ast.parse(HOOKS.read_text())
		for node in tree.body:
			if isinstance(node, ast.Assign) and node.targets[0].id == "PURCHASE_RECEIPT_SETTERS":
				return [tuple(ast.literal_eval(e)) for e in node.value.elts]

	def test_every_listed_setter_is_in_the_fixtures_with_the_right_value(self):
		fixtures = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		listed = self._hooks_tuple()
		self.assertGreater(len(listed), 100)
		for doctype, field, prop in listed:
			setter = fixtures[f"{doctype}-{field}-{prop}"]
			self.assertEqual((setter["doc_type"], setter["field_name"], setter["property"]), (doctype, field, prop))
			if prop == "hidden":
				self.assertEqual(setter["value"], "1", field)

	def test_what_the_staff_need_is_never_hidden(self):
		hidden = {(d, f) for d, f, p in self._hooks_tuple() if p == "hidden"}
		for doctype, fields in self.STAYS_VISIBLE.items():
			for field in fields:
				self.assertNotIn((doctype, field), hidden, field)

	def test_taxes_totals_and_technical_links_are_hidden(self):
		hidden = {(d, f) for d, f, p in self._hooks_tuple() if p == "hidden"}
		for field in ("taxes_section", "totals_section", "currency_and_price_list", "net_total", "base_total", "address_and_contact_tab", "is_return", "scan_barcode"):
			self.assertIn(("Purchase Receipt", field), hidden, field)
		for field in ("rejected_qty", "received_qty", "price_list_rate", "net_amount", "cost_center", "conversion_factor"):
			self.assertIn(("Purchase Receipt Item", field), hidden, field)
		self.assertTrue(fields()["Purchase Receipt-weigh_bridge_measurement"]["hidden"])
		self.assertTrue(fields()["Purchase Receipt-quality_check"]["hidden"])

	def test_the_company_list_is_limited_and_the_cost_center_is_aligned(self):
		script = (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text()
		self.assertIn("legal_company_query", script)
		self.assertIn('"Purchase Receipt": "public/js/purchase_receipt_mill.js"', HOOKS.read_text())
		import inspect

		self.assertIn("align_cost_center_with_company(doc)", inspect.getsource(pr.validate_purchase_receipt))


class TestSameRulesAsThePurchaseOrder(unittest.TestCase):
	def _doc(self, **values):
		base = dict(items=[FakeRow(item_code="PADDY", uom="Bags", qty=10, rate=100, idx=1)], hamali_payer="Yes", gunny_condition="Gunny Cut", dust_condition="Yes")
		base.update(values)
		return FakeDoc(base)

	def test_a_valid_receipt_passes_and_keeps_its_answers(self):
		d = self._doc()
		pr.apply_order_rules(d)
		self.assertEqual((d.gunny_condition, d.dust_condition, d.hamali_payer), ("Gunny Cut", "Yes", "Yes"))

	def test_answers_that_do_not_apply_are_cleared(self):
		d = self._doc(items=[FakeRow(item_code="HUSK", uom="Trip", qty=1, rate=100, avg_wt=25, idx=1)], quality_pds_rate_1=5)
		pr.apply_order_rules(d)
		self.assertEqual((d.gunny_condition, d.dust_condition, d.hamali_payer, d.quality_pds_rate_1), ("", "", "", 0))

	def test_the_order_rules_are_refused_on_the_receipt_too(self):
		bad = {
			"uom": self._doc(items=[FakeRow(item_code="PADDY", uom="Kg", qty=1, rate=1, idx=1)]),
			"quality": self._doc(items=[FakeRow(item_code="BOILED-RICE", uom="Quintal", qty=1, rate=1, idx=1)]),
			"rate": self._doc(items=[FakeRow(item_code="PADDY", uom="Quintal", qty=1, rate=0, idx=1)]),
			"trip avg wt": self._doc(items=[FakeRow(item_code="HUSK", uom="Trip", qty=1, rate=1, avg_wt=0, idx=1)]),
			"hamali payer": self._doc(hamali_payer=""),
		}
		for name, doc in bad.items():
			with self.assertRaises(frappe.ValidationError, msg=name):
				pr.apply_order_rules(doc)

	def test_a_pds_row_may_go_without_a_rate(self):
		pr.apply_order_rules(self._doc(items=[FakeRow(item_code="BOILED-RICE", uom="Quintal", qty=1, rate=0, quality="PDS", idx=1)], hamali_payer="", gunny_condition=""))

	def test_the_purchase_order_is_taken_from_the_items(self):
		d = FakeDoc(items=[FakeRow(purchase_order="PO-1"), FakeRow(purchase_order="PO-1")])
		pr.link_purchase_order(d)
		self.assertEqual(d.purchase_order, "PO-1")
		d = FakeDoc(items=[FakeRow(purchase_order="PO-1"), FakeRow(purchase_order="PO-2")])
		pr.link_purchase_order(d)
		self.assertIsNone(d.purchase_order)
		d = FakeDoc(purchase_order="PO-9", items=[FakeRow(purchase_order="PO-1")])
		pr.link_purchase_order(d)
		self.assertEqual(d.purchase_order, "PO-9")

	def test_the_trip_amount_and_the_typed_rate_rules_cover_the_receipt(self):
		from ivri_od.procurement import purchase_order_mill as po

		self.assertEqual(po.RULE_DOCTYPES, ("Purchase Order", "Purchase Receipt", "Purchase Invoice"))
		fixtures = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		self.assertEqual(fixtures["Purchase Receipt Item-rate-reqd"]["value"], "0")
		self.assertEqual(fixtures["Purchase Receipt Item-rate-mandatory_depends_on"]["value"], fixtures["Purchase Order Item-rate-mandatory_depends_on"]["value"])
		f = fields()
		self.assertEqual(f["Purchase Receipt Item-quality"]["depends_on"], json.loads((ROOT / "fixtures" / "custom_field.json").read_text())[[d["name"] for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text())].index("Purchase Order Item-quality")]["depends_on"])
		self.assertIn("mandatory_depends_on", f["Purchase Receipt-hamali_payer"])


class TestFetchFromThePurchaseOrder(unittest.TestCase):
	def test_the_script_fetches_the_items_and_follows_the_order_script(self):
		script = (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text()
		self.assertIn("frappe.model.mapper.map_docs", script)
		self.assertIn("make_purchase_receipt", script)
		self.assertIn('frm.clear_table("items")', script)
		order = (ROOT / "public" / "js" / "purchase_order_mill.js").read_text()
		for name in ("ITEM_RULES", "apply_item_rules", "update_hamali_section", "update_pds_rates", "update_dust_field", "update_gunny_field", "set_default_avg_wt", "follow_erpnext_total", "limit_item_uoms"):
			self.assertIn(name, script, name)
		self.assertTrue(script.index("(function () {") < script.index("const ITEM_RULES"))  # wrapped: no clash with the order script
		self.assertEqual(json.loads(order[order.index("const ITEM_RULES = ") + len("const ITEM_RULES = "): order.index("};\nconst DEFAULT_DIMENSION") + 1]), json.loads(script[script.index("const ITEM_RULES = ") + len("const ITEM_RULES = "): script.index("};\nconst DEFAULT_DIMENSION") + 1]))


class TestRateCanBeChangedOnTheReceipt(unittest.TestCase):
	def test_the_patch_switches_off_maintain_same_rate_and_is_listed(self):
		source = (ROOT / "patches" / "v1_0" / "allow_rate_change_on_receipt.py").read_text()
		self.assertIn('set_single_value("Buying Settings", "maintain_same_rate", 0)', source)
		self.assertIn("ivri_od.patches.v1_0.allow_rate_change_on_receipt", (ROOT / "patches.txt").read_text())


class TestVehicleSectionFromThePurchaseOrder(unittest.TestCase):
	NAMES = ("vehicle_ownership", "transporter", "vehicle_number", "driver", "freight_charges")

	def test_the_fields_carry_the_order_names_and_follow_the_ownership(self):
		allf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text())}
		for name in self.NAMES:
			receipt = allf[f"Purchase Receipt-{name}"]
			self.assertEqual(receipt["fieldtype"], allf[f"Purchase Order-{name}"]["fieldtype"], name)
			self.assertEqual(receipt.get("options"), allf[f"Purchase Order-{name}"].get("options"), name)
			if name != "vehicle_ownership":
				self.assertEqual(receipt["depends_on"], "eval:doc.vehicle_ownership=='Transport Vehicle'", name)
			self.assertIn(f"Purchase Receipt-{name}", HOOKS.read_text())
			self.assertNotEqual(receipt.get("hidden"), 1, name)
		order = [allf[f"Purchase Receipt-{n}"]["insert_after"] for n in ("vehicle_ownership", "transporter", "vehicle_number", "freight_charges")]
		self.assertEqual(order, ["receipt_vehicle_section", "vehicle_ownership", "transporter", "driver"])

	def test_an_owned_vehicle_clears_the_transport_details(self):
		d = FakeDoc(items=[FakeRow(item_code="PADDY", uom="Quintal", qty=1, rate=5, idx=1)], vehicle_ownership="Owned Vehicle", transporter="T", vehicle_number="CG04", driver="D", freight_charges=500)
		pr.apply_order_rules(d)
		self.assertEqual((d.transporter, d.vehicle_number, d.driver, d.freight_charges), (None, None, None, 0))
		d = FakeDoc(items=[FakeRow(item_code="PADDY", uom="Quintal", qty=1, rate=5, idx=1)], vehicle_ownership="Transport Vehicle", transporter="T", vehicle_number="CG04", driver="D", freight_charges=500)
		pr.apply_order_rules(d)
		self.assertEqual((d.transporter, d.vehicle_number, d.driver, d.freight_charges), ("T", "CG04", "D", 500))

	def test_a_negative_freight_or_hamali_rate_is_refused(self):
		for field in ("freight_charges", "hamali_rate"):
			d = FakeDoc(items=[FakeRow(item_code="PADDY", uom="Quintal", qty=1, rate=5, idx=1)])
			d[field] = -1
			with self.assertRaises(frappe.ValidationError, msg=field):
				pr.apply_order_rules(d)

	def test_the_script_lists_transporters_and_clears_on_ownership(self):
		script = (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text()
		self.assertIn("is_transporter: 1", script)
		self.assertIn("vehicle_ownership(frm)", script)


class TestLayoutFollowsThePurchaseOrder(unittest.TestCase):
	def setUp(self):
		ps = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		self.order = json.loads(ps["Purchase Receipt-main-field_order"]["value"])

	def test_every_field_is_listed_once(self):
		self.assertEqual(len(self.order), len(set(self.order)))
		self.assertIn("Purchase Receipt-main-field_order", HOOKS.read_text())

	def test_the_sections_run_in_the_order_of_the_purchase_order_form(self):
		o = self.order
		sequence = ["supplier_section", "sec_warehouse", "items", "section_break0", "receipt_conditions_section", "receipt_vehicle_section", "receipt_quality_section", "receipt_hamali_section", "receipt_deal_section", "receipt_final_section"]
		positions = [o.index(name) for name in sequence]
		self.assertEqual(positions, sorted(positions))
		self.assertEqual(o[o.index("items") + 1:o.index("items") + 6], ["quality_pds_percentage", "quality_pds_section", "quality_pds_rate_1", "quality_pds_rate_2", "quality_pds_rate_3"])
		self.assertLess(o.index("net_total"), o.index("receipt_conditions_section"))  # the totals come before the conditions, as on the order

	def test_the_status_sits_beside_the_company_and_the_final_section_is_named_like_the_order(self):
		o = self.order
		self.assertEqual(o.index("receipt_status"), o.index("print_company_name") + 1)
		self.assertEqual(o.index("set_warehouse"), o.index("company") + 1)  # the Warehouse sits just below the Company
		f = fields()
		self.assertEqual((f["Purchase Receipt-receipt_final_section"]["label"], f["Purchase Receipt-total_final_amount"]["label"]), ("Final Bill Amount", "Grand Total (Final Amount)"))
		self.assertEqual(f["Purchase Receipt-receipt_status"]["insert_after"], "print_company_name")


class FakeMetaRow(FakeRow):
	class meta:
		@staticmethod
		def get_field(fieldname):
			return True


class TestOrderedQtyFromThePurchaseOrder(unittest.TestCase):
	def test_the_order_quantity_goes_to_ordered_qty_and_received_is_left_empty(self):
		rows = [FakeMetaRow(purchase_order_item="POI-1", qty=60, received_qty=60, amount=600), FakeMetaRow(purchase_order_item="POI-2", qty=5, received_qty=5, amount=50)]
		with patch.object(frappe.db, "get_value", side_effect=lambda dt, name, field, as_dict=False: ({"POI-1": 100, "POI-2": 5}[name] if not as_dict else {"qty": {"POI-1": 100, "POI-2": 5}[name], "rate": 10})):
			pr.move_quantity_to_ordered(rows)
		self.assertEqual([(r.ordered_qty, r.qty, r.received_qty, r.amount) for r in rows], [(100, 0, 0, 0), (5, 0, 0, 0)])

	def test_rows_already_filled_in_or_not_from_an_order_are_left_alone(self):
		kept = FakeMetaRow(purchase_order_item="POI-1", ordered_qty=100, qty=40)
		manual = FakeMetaRow(qty=7)
		pr.move_quantity_to_ordered([kept, manual])
		self.assertEqual((kept.ordered_qty, kept.qty, manual.qty), (100, 40, 7))

	def test_an_empty_received_quantity_is_refused_with_a_plain_message(self):
		with self.assertRaises(frappe.ValidationError):
			pr.require_received_quantity(FakeDoc(items=[FakeRow(purchase_order_item="POI-1", qty=0, idx=1)]))
		pr.require_received_quantity(FakeDoc(items=[FakeRow(purchase_order_item="POI-1", qty=3, idx=1), FakeRow(qty=0, idx=2)]))

	def test_the_step_is_wrapped_once_and_put_back(self):
		from erpnext.buying.doctype.purchase_order import purchase_order as module

		pr.uninstall_ordered_qty_on_receipt()
		real = module.make_purchase_receipt
		try:
			pr.install_ordered_qty_on_receipt()
			pr.install_ordered_qty_on_receipt()  # twice is the same as once
			self.assertIsNot(module.make_purchase_receipt, real)
			self.assertIs(module.make_purchase_receipt._ivri_od_original, real)
			pr.uninstall_ordered_qty_on_receipt()
			self.assertIs(module.make_purchase_receipt, real)
		finally:
			pr.install_ordered_qty_on_receipt()

	def test_it_is_wired_in_the_hooks(self):
		hooks = HOOKS.read_text()
		self.assertEqual(hooks.count("purchase_receipt_mill.install_ordered_qty_on_receipt"), 2)
		self.assertIn("purchase_receipt_mill.require_received_quantity", hooks)


class TestPdsQualitySplit(unittest.TestCase):
	def _doc(self, quantities=(600, 300, 100), rates=(3000, 2900, 2800), received=1000, **values):
		base = dict(items=[FakeRow(item_code="BOILED-RICE", uom="Quintal", quality="PDS", qty=received, rate=0, idx=1)], doctype="Purchase Receipt")
		for i, (q, r) in enumerate(zip(quantities, rates), 1):
			base[f"quality_pds_qty_{i}"] = q
			base[f"quality_pds_rate_{i}"] = r
		base.update(values)
		return FakeDoc(base)

	def test_the_amount_is_the_sum_of_quantity_times_rate_of_the_three_qualities(self):
		from ivri_od.procurement import purchase_order_mill as po

		self.assertEqual(po.pds_amount(self._doc()), 600 * 3000 + 300 * 2900 + 100 * 2800)  # 2,950,000
		self.assertEqual(po.pds_amount(self._doc(quantities=(0, 0, 0))), 0)

	def test_only_a_receipt_with_one_split_pds_row_gets_the_grade_amount(self):
		from ivri_od.procurement import purchase_order_mill as po

		d = self._doc()
		self.assertIs(po.pds_split_row(d), d["items"][0])
		self.assertIsNone(po.pds_split_row(self._doc(quantities=(0, 0, 0))))  # no split yet: the normal Quantity x Rate
		self.assertIsNone(po.pds_split_row(self._doc(doctype="Purchase Order")))
		two = self._doc()
		two["items"].append(FakeRow(item_code="RAW-RICE", uom="Quintal", quality="25% Broken PDS", qty=5, rate=0, idx=2))
		self.assertIsNone(po.pds_split_row(two))

	def test_a_matching_split_passes_and_sets_the_pds_amount(self):
		d = self._doc()
		pr.validate_pds_split(d, d["items"])
		self.assertEqual(d.quality_pds_amount, 2950000)

	def test_a_split_that_does_not_add_up_or_lacks_a_rate_is_refused(self):
		wrong = {
			"does not add up": self._doc(quantities=(600, 300, 50)),
			"negative": self._doc(quantities=(1100, -100, 0)),
			"no rate": self._doc(rates=(3000, 0, 2800)),
		}
		for name, d in wrong.items():
			with self.assertRaises(frappe.ValidationError, msg=name):
				pr.validate_pds_split(d, d["items"])
		two = self._doc()
		two["items"].append(FakeRow(item_code="RAW-RICE", uom="Quintal", quality="25% Broken PDS", qty=5, rate=0, idx=2))
		with self.assertRaises(frappe.ValidationError):
			pr.validate_pds_split(two, two["items"])

	def test_no_split_yet_is_allowed_to_save_but_not_to_submit(self):
		d = self._doc(quantities=(0, 0, 0))
		pr.validate_pds_split(d, d["items"])
		with self.assertRaises(frappe.ValidationError):
			pr.require_pds_split_on_submit(d)
		pr.require_pds_split_on_submit(self._doc())

	def test_without_a_pds_row_the_rates_quantities_and_amount_are_cleared(self):
		d = FakeDoc(items=[FakeRow(item_code="PADDY", uom="Quintal", quality="", qty=1, rate=5, idx=1)], quality_pds_qty_1=5, quality_pds_rate_1=9, quality_pds_amount=45)
		pr.apply_order_rules(d)
		self.assertEqual((d.quality_pds_qty_1, d.quality_pds_rate_1, d.quality_pds_amount), (0, 0, 0))

	def test_fields_layout_print_and_script_are_in_place(self):
		f = fields()
		for name in ("quality_pds_qty_1", "quality_pds_qty_2", "quality_pds_qty_3"):
			self.assertEqual(f[f"Purchase Receipt-{name}"]["fieldtype"], "Float")
			self.assertIn(f"Purchase Receipt-{name}", HOOKS.read_text())
		self.assertEqual(f["Purchase Receipt-quality_pds_rate_1"]["insert_after"], "quality_pds_section")
		self.assertTrue(f["Purchase Receipt-quality_pds_amount"]["read_only"])
		ps = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		order = json.loads(ps["Purchase Receipt-main-field_order"]["value"])
		i = order.index("quality_pds_percentage")
		self.assertEqual(order[i:i + 14], ["quality_pds_percentage", "quality_pds_section", "quality_pds_rate_1", "quality_pds_rate_2", "quality_pds_rate_3", "quality_pds_pct_col", "quality_pds_pct_1", "quality_pds_pct_2", "quality_pds_pct_3", "quality_pds_col", "quality_pds_qty_1", "quality_pds_qty_2", "quality_pds_qty_3", "quality_pds_amount"])
		html = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Purchase Receipt - Shyamji"]["html"]
		self.assertIn("quality_pds_qty_1", html)
		script = (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text()
		self.assertIn("PDS_QTY_FIELDS", script)
		self.assertIn("quality_pds_qty_3(frm)", script)
		self.assertIn("purchase_receipt_mill.require_pds_split_on_submit", HOOKS.read_text())


class TestPdsReceivedQuantityIsTheSum(unittest.TestCase):
	def _doc(self, quantities, received=0, quality="PDS"):
		d = FakeDoc(items=[FakeRow(item_code="BOILED-RICE", uom="Quintal", quality=quality, qty=received, received_qty=received, rate=0, idx=1)])
		for i, q in enumerate(quantities, 1):
			d[f"quality_pds_qty_{i}"] = q
		d["items"][0].precision = lambda f: None
		return d

	def test_the_received_quantity_becomes_the_sum_of_the_three(self):
		d = self._doc((600, 300, 100), received=0)
		pr.sync_pds_quantity(d)
		self.assertEqual((d["items"][0].qty, d["items"][0].received_qty), (1000, 1000))

	def test_a_typed_quantity_is_replaced_by_the_sum_once_the_split_is_filled(self):
		d = self._doc((600, 300, 100), received=900)
		pr.sync_pds_quantity(d)
		self.assertEqual(d["items"][0].qty, 1000)

	def test_without_a_split_or_a_pds_row_the_typed_quantity_stays(self):
		d = self._doc((0, 0, 0), received=900)
		pr.sync_pds_quantity(d)
		self.assertEqual(d["items"][0].qty, 900)
		d = self._doc((600, 300, 100), received=50, quality="Fresh Milling")
		pr.sync_pds_quantity(d)
		self.assertEqual(d["items"][0].qty, 50)

	def test_the_sum_is_filled_before_the_empty_quantity_check_and_the_screen_does_it_too(self):
		hooks = HOOKS.read_text()
		self.assertLess(hooks.index("purchase_receipt_mill.sync_pds_quantity"), hooks.index("purchase_receipt_mill.require_received_quantity"))
		script = (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text()
		self.assertGreaterEqual(script.count("sync_pds_quantity(frm);"), 3)  # the three quantities and the three percentages
		self.assertIn("keep_pds_quantity(frm, cdt, cdn);", script)


class TestPdsPercentageTickBox(unittest.TestCase):
	def _doc(self, ticked, pcts=(60, 30, 10), ordered=1000, quantities=(0, 0, 0)):
		row = FakeRow(item_code="BOILED-RICE", uom="Quintal", quality="PDS", qty=0, received_qty=0, ordered_qty=ordered, rate=0, idx=1)
		row.precision = lambda f: None
		d = FakeDoc(items=[row], quality_pds_percentage=1 if ticked else 0)
		for i, (p, q) in enumerate(zip(pcts, quantities), 1):
			d[f"quality_pds_pct_{i}"] = p
			d[f"quality_pds_qty_{i}"] = q
		return d

	def test_ticked_the_percentages_of_the_ordered_qty_become_the_three_quantities(self):
		d = self._doc(True)
		pr.sync_pds_quantity(d)
		self.assertEqual([d["quality_pds_qty_1"], d["quality_pds_qty_2"], d["quality_pds_qty_3"]], [600, 300, 100])
		self.assertEqual(d["items"][0].qty, 1000)

	def test_the_sum_may_be_less_than_the_order(self):
		d = self._doc(True, pcts=(50, 20, 0))
		pr.sync_pds_quantity(d)
		self.assertEqual(d["items"][0].qty, 700)

	def test_not_ticked_the_quantities_are_used_and_the_percentages_ignored(self):
		d = self._doc(False, pcts=(60, 30, 10), quantities=(5, 5, 5))
		pr.sync_pds_quantity(d)
		self.assertEqual([d["quality_pds_qty_1"], d["quality_pds_qty_2"], d["quality_pds_qty_3"]], [5, 5, 5])
		self.assertEqual(d["items"][0].qty, 15)

	def test_a_percentage_without_an_order_or_a_negative_one_is_refused(self):
		for name, d in {"no order": self._doc(True, ordered=0), "negative": self._doc(True, pcts=(110, -10, 0))}.items():
			with patch.object(frappe.db, "get_value", return_value=0), self.assertRaises(frappe.ValidationError, msg=name):
				pr.sync_pds_quantity(d)

	def test_without_a_pds_row_the_percentages_and_the_tick_are_reset(self):
		d = FakeDoc(items=[FakeRow(item_code="PADDY", uom="Quintal", quality="", qty=1, rate=5, idx=1)], quality_pds_percentage=1, quality_pds_pct_1=50)
		pr.apply_order_rules(d)
		self.assertEqual((d.quality_pds_pct_1, d.quality_pds_percentage), (0, 0))

	def test_the_tick_box_the_read_only_rule_and_the_script_are_in_place(self):
		f = fields()
		box = f["Purchase Receipt-quality_pds_percentage"]
		self.assertEqual((box["fieldtype"], box["default"], box["insert_after"]), ("Check", "0", "items"))
		self.assertNotIn("Purchase Receipt-quality_pds_entry", f)
		for i in (1, 2, 3):
			self.assertEqual(f[f"Purchase Receipt-quality_pds_pct_{i}"]["depends_on"], "eval:doc.quality_pds_percentage")
			self.assertEqual(f[f"Purchase Receipt-quality_pds_qty_{i}"]["read_only_depends_on"], "eval:doc.quality_pds_percentage")
			self.assertIn(f"Purchase Receipt-quality_pds_pct_{i}", HOOKS.read_text())
		script = (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text()
		for name in ("quantities_from_percentages", "percentages_from_quantities", "quality_pds_percentage(frm)", "quality_pds_pct_3(frm)"):
			self.assertIn(name, script, name)
		self.assertIn("remove_pds_entry_select", (ROOT / "patches.txt").read_text())


class TestWarehouseUnderCompanyAndNoRowStatus(unittest.TestCase):
	def test_the_row_status_is_hidden_from_the_form_but_still_worked_out(self):
		f = fields()
		row = f["Purchase Receipt Item-receipt_status"]
		self.assertEqual((row["hidden"], row["in_list_view"]), (1, 0))
		self.assertTrue(f["Purchase Receipt-receipt_status"]["in_list_view"])  # the receipt's own status stays
		self.assertIn("row.receipt_status", __import__("inspect").getsource(pr.validate_purchase_receipt))

	def test_the_items_section_header_is_hidden_and_the_item_column_is_wider(self):
		ps = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		self.assertEqual(ps["Purchase Receipt-sec_warehouse-hidden"]["value"], "1")
		self.assertEqual(ps["Purchase Receipt Item-item_code-columns"]["value"], "2")
		columns = {"item_code": 2, "quality": 2, "qty": 1, "ordered_qty": 1, "uom": 1, "rate": 1, "amount": 2}
		self.assertEqual(sum(columns.values()), 10)  # an ordinary table; Frappe shares the width in proportion if a Rice Bran table adds its oil columns
		self.assertEqual(ps["Purchase Receipt Item-amount-columns"]["value"], "2")  # room for an amount such as 12,38,400.00


class TestPrintFormatIsTheOrdersFormat(unittest.TestCase):
	def setUp(self):
		formats = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}
		self.order, self.receipt = formats["Purchase Order - Shyamji"], formats["Purchase Receipt - Shyamji"]

	def test_the_look_is_the_orders_look(self):
		for key in ("css", "margin_top", "margin_bottom", "margin_left", "margin_right", "font_size", "page_number", "pdf_generator"):
			self.assertEqual(self.receipt[key], self.order[key], key)

	def test_every_block_of_the_order_print_is_on_the_receipt_print(self):
		for block in ('class="po-head"', 'class="po-bar"', 'class="po-bar-yellow"', 'class="po-two"', 'po-box-title">Supplier', 'class="po-two po-vehicle"', 'class="po-items"', 'class="po-two po-after"',
				'class="po-totals"', 'class="po-final"', 'class="po-words"', 'class="po-terms"', 'class="po-sign"', 'class="po-foot"', "Prepared By", "Checked By", "Authorised Signatory", "Total Final Amount (INR)"):
			self.assertIn(block, self.order["html"], block)
			self.assertIn(block, self.receipt["html"], block)

	def test_the_receipt_print_is_the_default_format_of_the_receipt(self):
		ps = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		setter = ps["Purchase Receipt-main-default_print_format"]
		self.assertEqual((setter["doc_type"], setter["property"], setter["value"]), ("Purchase Receipt", "default_print_format", "Purchase Receipt - Shyamji"))
		self.assertIn("Purchase Receipt-main-default_print_format", HOOKS.read_text())
		self.assertEqual(self.receipt["html"].count("if show_company"), 2)


class TestGunnyOnlyForFourItems(unittest.TestCase):
	def _gunny(self, item, quality=""):
		d = FakeDoc(items=[FakeRow(item_code=item, uom="Bags", qty=1, rate=5, idx=1, quality=quality)], gunny_condition="Gunny Cut", hamali_payer="Yes")
		pr.apply_order_rules(d)
		return d.gunny_condition

	def test_gunny_is_kept_for_paddy_and_the_rice_items_and_cleared_for_others(self):
		self.assertEqual(self._gunny("PADDY"), "Gunny Cut")
		self.assertEqual(self._gunny("MURI-RICE"), "Gunny Cut")
		self.assertEqual(self._gunny("BOILED-RICE", "Fresh Milling"), "Gunny Cut")
		self.assertEqual(self._gunny("HUSK"), "")


class TestDealAndDifference(unittest.TestCase):
	def _receipt(self, **values):
		base = dict(doctype="Purchase Receipt", purchase_order="PO-1", total_hamali=0, discount_amount=0, total_final_amount=0)
		base.update(values)
		return FakeDoc(base)

	def _row(self, **values):
		base = dict(purchase_order_item="POI-1", item_code="PADDY", uom="Quintal", qty=100, po_rate=2300, amount=0, avg_wt=0)
		base.update(values)
		return FakeRow(base)

	def test_the_deal_amount_is_the_goods_received_at_the_order_rates(self):
		d = self._receipt(items=[self._row(qty=60)])
		self.assertEqual(pr.deal_amount(d), 60 * 2300)

	def test_a_rice_bran_row_is_valued_at_its_quoted_rate_per_mt(self):
		d = self._receipt(items=[self._row(item_code="RICE-BRAN", qty=300, rate_per_mt=48000, po_rate=4800)])
		self.assertEqual(pr.deal_amount(d), 30 * 48000)  # 14,40,000
		d = self._receipt(items=[self._row(item_code="RICE-BRAN", uom="Trip", qty=2, avg_wt=25, rate_per_mt=48000)])
		self.assertEqual(pr.deal_amount(d), 2 * 25 * 48000)

	def test_a_trip_row_and_the_hamali_and_discount(self):
		d = self._receipt(items=[self._row(uom="Trip", qty=2, avg_wt=25, po_rate=2000)], total_hamali=100, discount_amount=50)
		self.assertEqual(pr.deal_amount(d), 2 * 25 * 10 * 2000 - 150)

	def test_a_pds_row_is_valued_grade_by_grade_so_it_matches_the_receipt(self):
		d = self._receipt(items=[self._row(item_code="BOILED-RICE", quality="PDS", qty=1000, amount=2950000)])
		self.assertEqual(pr.deal_amount(d), 2950000)

	def test_the_boiled_bran_example_shows_the_difference_of_the_clients_notes(self):
		d = self._receipt(items=[self._row(item_code="RICE-BRAN", qty=300, rate_per_mt=48000, po_rate=4800)], total_final_amount=1238400)
		d.precision = lambda f: None
		with patch.object(frappe.db, "get_value", return_value=1440000):
			pr.set_deal_fields(d)
		self.assertEqual((d.deal_amount, d.amount_difference), (1440000, -201600))  # 30 MT x 6,720

	def test_a_part_delivery_is_not_compared_with_the_whole_order(self):
		d = self._receipt(items=[self._row(qty=40)], total_final_amount=40 * 2300)
		d.precision = lambda f: None
		with patch.object(frappe.db, "get_value", return_value=100 * 2300):
			pr.set_deal_fields(d)
		self.assertEqual((d.deal_amount, d.amount_difference), (92000, 0))

	def test_without_a_purchase_order_nothing_is_compared(self):
		d = self._receipt(purchase_order=None, items=[self._row()], total_final_amount=500)
		pr.set_deal_fields(d)
		self.assertEqual((d.deal_amount, d.amount_difference), (0, 0))

	def test_the_fields_the_layout_and_the_script(self):
		f = fields()
		for name in ("deal_amount", "amount_difference"):
			self.assertTrue(f[f"Purchase Receipt-{name}"]["read_only"], name)
			self.assertEqual(f[f"Purchase Receipt-{name}"]["depends_on"], "eval:doc.purchase_order", name)
			self.assertIn(f"Purchase Receipt-{name}", HOOKS.read_text())
		self.assertNotIn("Purchase Receipt-po_grand_total", f)  # the PO Grand Total is not shown on the receipt
		self.assertEqual(f["Purchase Receipt Item-po_rate"]["hidden"], 1)
		ps = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		order = json.loads(ps["Purchase Receipt-main-field_order"]["value"])
		i = order.index("receipt_final_section")
		j = order.index("receipt_deal_section")
		self.assertEqual(order[j:j + 6], ["receipt_deal_section", "deal_amount", "receipt_final_col", "amount_difference", "receipt_final_section", "total_final_amount"])
		self.assertEqual(order[i:i + 2], ["receipt_final_section", "total_final_amount"])
		visible = [f for f in order if f in ("receipt_hamali_section", "receipt_deal_section", "receipt_final_section")]
		self.assertEqual(visible, ["receipt_hamali_section", "receipt_deal_section", "receipt_final_section"])
		script = (ROOT / "public" / "js" / "purchase_receipt_mill.js").read_text()
		self.assertIn("function set_deal_amounts(frm)", script)
		self.assertIn('BRAN_COLUMNS = ["oil_percentage", "actual_oil_percentage"]', script)


class TestPoGrandTotalRemoved(unittest.TestCase):
	def test_the_field_is_gone_from_the_fixtures_the_code_and_the_site_patch_exists(self):
		for path in ("fixtures/custom_field.json", "fixtures/property_setter.json", "procurement/purchase_receipt_mill.py", "public/js/purchase_receipt_mill.js"):
			self.assertNotIn("po_grand_total", (ROOT / path).read_text(), path)
		self.assertNotIn("po_grand_total", HOOKS.read_text())
		self.assertIn("remove_po_grand_total_from_receipt", (ROOT / "patches.txt").read_text())


class TestGrandTotalIsAtTheBottom(unittest.TestCase):
	def test_the_grand_total_final_amount_is_the_last_field_of_the_main_form(self):
		ps = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		order = json.loads(ps["Purchase Receipt-main-field_order"]["value"])
		shown = ["quality_pds_amount", "gunny_condition", "vehicle_ownership", "moisture", "hamali_payer", "deal_amount", "amount_difference", "total_final_amount"]
		positions = [order.index(f) for f in shown]
		self.assertEqual(positions, sorted(positions))
		self.assertEqual(order[order.index("total_final_amount") + 1], "taxes_charges_section")  # only hidden sections come after it
		self.assertEqual(fields()["Purchase Receipt-total_final_amount"]["label"], "Grand Total (Final Amount)")
