# Copyright (c) 2026, Profezzo and contributors
"""Purchase Invoice: made from a Purchase Receipt or a Purchase Order, with the rules of both and the Hamali plus a Deduction Amount taken off."""

import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from ivri_od.procurement import purchase_invoice_mill as pi
from ivri_od.procurement import purchase_order_mill as po

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
		return None


def hooks_module():
	spec = importlib.util.spec_from_file_location("ivri_od_hooks", HOOKS)
	module = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(module)
	return module


def fields():
	return {d["name"]: d for d in json.loads((ROOT / "fixtures" / "custom_field.json").read_text()) if d["dt"].startswith("Purchase Invoice")}


def invoice(**values):
	base = dict(doctype="Purchase Invoice", items=[FakeDoc(item_code="PADDY", uom="Bags", qty=100, rate=2300, idx=1)], hamali_payer="Yes", hamali_rate=3, deduction_amount=0, total=230000)
	base.update(values)
	return FakeDoc(base)


class TestDeductions(unittest.TestCase):
	def test_hamali_and_the_deduction_become_the_additional_discount(self):
		d = invoice(deduction_amount=500)
		pi.set_deductions_as_discount(d)
		self.assertEqual((d.total_hamali, d.discount_amount), (300, 800))  # 100 bags x 3 + 500
		self.assertEqual((d.apply_discount_on, d.additional_discount_percentage, d.disable_rounded_total), ("Net Total", 0, 1))

	def test_no_hamali_when_the_hamali_paying_is_not_yes_or_there_are_no_bags(self):
		d = invoice(hamali_payer="No", deduction_amount=200)
		pi.set_deductions_as_discount(d)
		self.assertEqual((d.total_hamali, d.discount_amount), (0, 200))
		d = invoice(items=[FakeDoc(item_code="PADDY", uom="Quintal", qty=10, rate=5, idx=1)], deduction_amount=0)
		pi.set_deductions_as_discount(d)
		self.assertEqual((d.total_hamali, d.discount_amount), (0, 0))

	def test_a_negative_deduction_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			pi.set_deductions_as_discount(invoice(deduction_amount=-1))

	def test_the_final_amount_is_the_grand_total_and_the_documents_are_linked(self):
		d = invoice(grand_total=229700, items=[FakeDoc(item_code="PADDY", uom="Bags", qty=100, rate=2300, idx=1, purchase_order="PO-1", purchase_receipt="PR-1"),
			FakeDoc(item_code="PADDY", uom="Bags", qty=5, rate=2300, idx=2, purchase_order="PO-1", purchase_receipt="PR-1")])
		pi.validate_purchase_invoice(d)
		self.assertEqual((d.total_final_amount, d.purchase_order, d.purchase_receipt), (229700, "PO-1", "PR-1"))


class TestSameRulesAsTheOrderAndReceipt(unittest.TestCase):
	def test_the_rules_of_the_order_apply_to_an_invoice_row(self):
		for name, row in {"zero rate": dict(item_code="PADDY", uom="Quintal", qty=1, rate=0), "bad uom": dict(item_code="PADDY", uom="Kg", qty=1, rate=5),
				"quality missing": dict(item_code="BOILED-RICE", uom="Quintal", qty=1, rate=5)}.items():
			with self.assertRaises(frappe.ValidationError, msg=name):
				pi.apply_order_rules(invoice(items=[FakeDoc(idx=1, **row)], hamali_payer=""))

	def test_the_invoice_is_paid_on_the_oil_and_the_pds_qualities_like_the_receipt(self):
		self.assertEqual(po.RULE_DOCTYPES, ("Purchase Order", "Purchase Receipt", "Purchase Invoice"))
		self.assertEqual(po.PAID_BY_QUALITY_DOCTYPES, ("Purchase Receipt", "Purchase Invoice"))
		row = FakeDoc(item_code="RICE-BRAN", uom="Quintal", qty=300, rate_per_mt=48000, oil_percentage=25, actual_oil_percentage=21.5)
		row.precision = lambda f: None
		self.assertTrue(po.bran_oil_row(FakeDoc(doctype="Purchase Invoice"), row))
		self.assertFalse(po.bran_oil_row(FakeDoc(doctype="Purchase Order"), row))
		self.assertEqual(po.bran_amount(row), 30 * 41280)
		d = FakeDoc(doctype="Purchase Invoice", quality_pds_qty_1=600, quality_pds_qty_2=300, quality_pds_qty_3=100, items=[FakeDoc(quality="PDS")])
		self.assertIs(po.pds_split_row(d), d["items"][0])

	def test_the_ordered_qty_is_found_for_an_invoice_row_from_the_order_or_the_receipt(self):
		from ivri_od.procurement import purchase_receipt_mill as pr

		with patch.object(frappe.db, "get_value", return_value=100):
			self.assertEqual(pr.ordered_quantity(FakeDoc(po_detail="POI-1")), 100)
			self.assertEqual(pr.ordered_quantity(FakeDoc(pr_detail="PRI-1")), 100)
		self.assertEqual(pr.ordered_quantity(FakeDoc(ordered_qty=40)), 40)


class TestFixturesHooksScriptAndPrint(unittest.TestCase):
	def test_the_fields_have_the_same_names_as_the_order_and_receipt_so_erpnext_copies_them(self):
		f = fields()
		for name in ("gunny_condition", "dust_condition", "payment_mode", "delivery_type", "location_name", "vehicle_ownership", "transporter", "vehicle_number", "driver", "freight_charges",
				"hamali_payer", "hamali_rate", "total_hamali", "quality_pds_percentage", "quality_pds_rate_1", "quality_pds_qty_1", "quality_pds_pct_1", "quality_pds_amount", "moisture", "dust_kg", "print_company_name"):
			self.assertIn(f"Purchase Invoice-{name}", f, name)
		for name in ("quality", "dimension", "avg_wt", "rate_per_mt", "oil_percentage", "actual_oil_percentage", "oil_rate_per_mt", "ordered_qty"):
			self.assertIn(f"Purchase Invoice Item-{name}", f, name)
		self.assertEqual((f["Purchase Invoice-purchase_receipt"]["options"], f["Purchase Invoice-purchase_order"]["options"]), ("Purchase Receipt", "Purchase Order"))
		self.assertEqual((f["Purchase Invoice-deduction_amount"]["fieldtype"], f["Purchase Invoice-deduction_reason"]["depends_on"]), ("Currency", "eval:doc.deduction_amount"))
		self.assertTrue(f["Purchase Invoice-total_final_amount"]["read_only"])
		self.assertEqual(f["Purchase Invoice-total_final_amount"]["label"], "Grand Total (Final Amount)")

	def test_the_deduction_and_final_sections_come_last_and_everything_is_exported(self):
		f = fields()
		self.assertEqual(f["Purchase Invoice-invoice_quality_section"]["insert_after"], "freight_charges")  # the sections run one after the other: Vehicle, Quality, Hamali, Deductions, Final
		self.assertEqual(f["Purchase Invoice-invoice_hamali_section"]["insert_after"], "dust_kg")
		self.assertEqual(f["Purchase Invoice-invoice_deduction_section"]["insert_after"], "total_hamali")
		self.assertEqual(f["Purchase Invoice-invoice_final_section"]["insert_after"], "deduction_reason")
		self.assertEqual(f["Purchase Invoice-total_final_amount"]["insert_after"], "invoice_final_section")
		module = hooks_module()
		for name in f:
			self.assertIn(name, module.PURCHASE_INVOICE_CUSTOM_FIELDS, name)

	def test_the_form_shows_only_what_the_staff_need(self):
		module = hooks_module()
		hidden = {(d, f) for d, f, p in module.PURCHASE_INVOICE_SETTERS if p == "hidden"}
		for field in ("taxes_section", "currency_and_price_list", "address_and_contact_tab", "payments_tab", "update_stock", "is_return", "net_total", "base_total", "apply_tds"):
			self.assertIn(("Purchase Invoice", field), hidden, field)
		for field in ("rejected_qty", "price_list_rate", "net_amount", "cost_center", "conversion_factor", "warehouse", "expense_account"):
			self.assertIn(("Purchase Invoice Item", field), hidden, field)
		for field in ("supplier", "naming_series", "posting_date", "company", "items", "bill_no", "bill_date", "total", "total_qty", "due_date"):
			self.assertNotIn(("Purchase Invoice", field), hidden, field)
		for field in ("item_code", "item_name", "qty", "uom", "rate", "amount"):
			self.assertNotIn(("Purchase Invoice Item", field), hidden, field)
		setters = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "property_setter.json").read_text())}
		for dt, f, p in module.PURCHASE_INVOICE_SETTERS:
			self.assertIn(f"{dt}-{f}-{p}", setters, f"{dt}-{f}-{p}")
		self.assertEqual(setters["Purchase Invoice-main-default_print_format"]["value"], "Purchase Invoice - Shyamji")

	def test_events_installs_script_and_print_are_wired(self):
		hooks = HOOKS.read_text()
		for part in ("purchase_invoice_mill.set_deductions_as_discount", "purchase_invoice_mill.validate_purchase_invoice", "purchase_invoice_mill.install_ordered_qty_on_invoice",
				'"Purchase Invoice": "public/js/purchase_invoice_mill.js"', '"Purchase Invoice - Shyamji"'):
			self.assertIn(part, hooks, part)
		self.assertEqual(hooks.count("purchase_invoice_mill.install_ordered_qty_on_invoice"), 2)
		script = (ROOT / "public" / "js" / "purchase_invoice_mill.js").read_text()
		for part in ("make_purchase_invoice", "purchase_receipt(frm)", "purchase_order(frm)", "set_total_final_amount", "deduction_amount(frm)", "BRAN_OIL_DEFAULT", "quantities_from_percentages", "(function () {"):
			self.assertIn(part, script, part)
		self.assertNotIn("set_deal_amounts", script)
		html = {d["name"]: d["html"] for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Purchase Invoice - Shyamji"]
		for part in ("PURCHASE INVOICE", "Invoice Details", "Supplier Bill No.", "Less: Deduction", "Total Final Amount (INR)", "Prepared By"):
			self.assertIn(part, html, part)
		self.assertNotIn("Cash Discount", html)
