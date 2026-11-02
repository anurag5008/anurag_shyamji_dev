# Copyright (c) 2026, Profezzo and contributors
"""Purchase Invoice: made from a Purchase Receipt or straight from a Purchase Order. It follows the rules of both: the fields carry the same
names, so ERPNext copies them across (Quality, Dimension, Avg Wt, Rice Bran Rate Per MT and Oil Percentage, the PDS qualities, Conditions,
Hamali, Vehicle, Payment Mode). The Hamali and a typed Deduction Amount are taken off what is payable (as the Additional Discount), so the
supplier's account shows the Grand Total (Final Amount)."""

import functools

import frappe
from frappe.utils import flt

from ivri_od.procurement.purchase_order_mill import (
	HAMALI_PAYING,
	align_cost_center_with_company,
	hamali_bags,
	total_hamali,
)
from ivri_od.procurement.purchase_receipt_mill import apply_order_rules


def deductions(doc):
	"""What is taken off the Total: the Hamali (when the Hamali Paying is Yes) plus the Deduction Amount typed for a shortage, return or claim."""
	hamali = 0
	if doc.get("hamali_payer") == HAMALI_PAYING:
		hamali = total_hamali(hamali_bags(doc.get("items")), doc.get("hamali_rate"), doc.precision("total_hamali"))
	return hamali, flt(doc.get("deduction_amount"))


def set_deductions_as_discount(doc, method=None):
	"""Hamali and the Deduction Amount become the Additional Discount before ERPNext works the totals out, so the payable amount is the final one."""
	if flt(doc.get("deduction_amount")) < 0:
		frappe.throw(frappe._("The Deduction Amount cannot be negative."))
	hamali, deduction = deductions(doc)
	doc.total_hamali = hamali
	doc.apply_discount_on = "Net Total"
	doc.additional_discount_percentage = 0
	doc.discount_amount = flt(hamali + deduction, doc.precision("discount_amount"))
	doc.disable_rounded_total = 1  # the amount payable is the exact Grand Total (Final Amount)


def validate_purchase_invoice(doc, method=None):
	align_cost_center_with_company(doc)
	apply_order_rules(doc)
	doc.total_final_amount = flt(doc.get("grand_total"), doc.precision("total_final_amount"))
	link_documents(doc)


def link_documents(doc):
	"""An invoice made with the Create button has no Purchase Order or Purchase Receipt on top: take them from the Items when they all come from one."""
	for field, row_field in (("purchase_order", "purchase_order"), ("purchase_receipt", "purchase_receipt")):
		if doc.get(field):
			continue
		found = {row.get(row_field) for row in doc.get("items") or [] if row.get(row_field)}
		if len(found) == 1:
			doc.set(field, found.pop())


def install_ordered_qty_on_invoice(*args, **kwargs):
	"""An invoice made straight from a Purchase Order gets the order quantity as the Ordered Qty of each row (the PDS percentage is a percentage of it).
	This wraps the step that makes the invoice (ERPNext is not edited). Safe to call any number of times; called by before_request and before_job."""
	from erpnext.buying.doctype.purchase_order import purchase_order

	original = purchase_order.make_purchase_invoice
	if getattr(original, "_ivri_od_ordered_qty", None):
		return

	@functools.wraps(original)
	def make_purchase_invoice(source_name, target_doc=None, args=None):
		doc = original(source_name, target_doc, args)
		for row in doc.get("items") or []:
			if not row.get("ordered_qty") and row.get("po_detail"):
				row.ordered_qty = flt(frappe.db.get_value("Purchase Order Item", row.po_detail, "qty"))
		doc.purchase_order = doc.get("purchase_order") or source_name
		return doc

	make_purchase_invoice._ivri_od_ordered_qty = True
	make_purchase_invoice._ivri_od_original = original
	purchase_order.make_purchase_invoice = frappe.whitelist()(make_purchase_invoice)


def uninstall_ordered_qty_on_invoice():
	"""Put ERPNext's own step back (used by tests)."""
	from erpnext.buying.doctype.purchase_order import purchase_order

	step = purchase_order.make_purchase_invoice
	if getattr(step, "_ivri_od_ordered_qty", None):
		purchase_order.make_purchase_invoice = step._ivri_od_original
