# Copyright (c) 2026, Profezzo and contributors
"""Purchase Receipt: made from a Purchase Order, which hands its details over (the fields carry the same names on both
documents, so ERPNext copies them: Quality, Dimension, Avg Wt, Conditions, Hamali, Payment Mode, Rate). Several receipts can
belong to one order. This works out each row's Ordered Qty and Status, the receipt's status, the hamali and the Final Amount."""

import functools

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.purchase_order_mill import (
	ASK_TRANSPORT_DETAILS,
	BAG_UOMS,
	BRAN_ITEM,
	QUINTAL_PER_MT,
	DUST_ITEM,
	GUNNY_ITEMS,
	HAMALI_PAYING,
	PDS_QUALITY,
	NON_NEGATIVE,
	PDS_QTY_FIELDS,
	PDS_RATE_FIELDS,
	TRANSPORT_FIELDS,
	TRANSPORT_VEHICLE,
	TRIP_UOM,
	align_cost_center_with_company,
	hamali_bags,
	total_final_amount,
	pds_amount,
	total_hamali,
	validate_item_quality_dimension,
	validate_item_rate,
	validate_item_uoms,
	validate_transport_details,
	validate_trip_avg_wt,
)

PENDING = "Partly Received"
COMPLETE = "Fully Received"
EXCESS = "Excess"
STATUS_RANK = {COMPLETE: 1, PENDING: 2, EXCESS: 3}  # the receipt shows the row status that needs the most attention


def item_status(ordered, earlier, received, precision=None):
	"""Status of an order line once this receipt is counted: what earlier receipts brought plus this one against the ordered quantity."""
	ordered = flt(ordered, precision)
	if not ordered:
		return ""
	difference = flt(flt(earlier) + flt(received) - ordered, precision)
	if difference > 0:
		return EXCESS
	return COMPLETE if difference == 0 else PENDING


def receipt_status(statuses):
	"""The receipt's status is the row status that needs the most attention (Excess, then Partly Received, then Fully Received)."""
	return max((s for s in statuses if s), key=lambda s: STATUS_RANK[s], default="")


def apply_order_rules(doc):
	"""The rules of the Purchase Order form, held on the receipt too: UOM, Quality and Dimension by Item, Avg Wt of a Trip, a Rate on every
	row except a PDS one, and the answers (Gunny, Dust, PDS Rates, Hamali, the Vehicle details) that are kept only while they apply."""
	items = doc.get("items") or []
	validate_item_uoms(doc)
	validate_item_quality_dimension(doc)
	validate_trip_avg_wt(doc)
	validate_item_rate(doc)
	if any(row.get("uom") == TRIP_UOM for row in items) or not any(row.get("item_code") in GUNNY_ITEMS for row in items):
		doc.gunny_condition = ""  # Gunny is not asked for a Trip, nor for an Item other than Boiled Rice, Raw Rice, Muri Rice and Paddy
	pds_rows = [row for row in items if PDS_QUALITY in (row.get("quality") or "")]
	if not pds_rows:
		for fieldname in (*PDS_RATE_FIELDS, *PDS_QTY_FIELDS, *PDS_PCT_FIELDS):
			doc.set(fieldname, 0)  # the PDS rates, quantities and percentages are asked only while a row's Quality is PDS
		doc.quality_pds_amount = 0
		doc.quality_pds_percentage = 0
	else:
		validate_pds_split(doc, pds_rows)
	if not any(row.get("item_code") == DUST_ITEM for row in items):
		doc.dust_condition = ""  # Dust is asked only for Paddy
	if not any(row.get("uom") in BAG_UOMS for row in items):
		doc.hamali_payer = ""  # no Bags row: the Hamali section is hidden, so nothing may stay behind
	elif not doc.get("hamali_payer"):
		frappe.throw(_("Hamali Paying is required when the UOM is Bags."))
	for fieldname, label in NON_NEGATIVE:
		if flt(doc.get(fieldname)) < 0:
			frappe.throw(_("{0} cannot be negative.").format(_(label)))
	if doc.get("vehicle_ownership") == TRANSPORT_VEHICLE:
		if ASK_TRANSPORT_DETAILS:
			validate_transport_details(doc)
	else:
		# an Owned Vehicle (or none) has no transporter, so old transport details must not stay behind
		for fieldname, _label in TRANSPORT_FIELDS:
			doc.set(fieldname, None)
		doc.freight_charges = 0


def validate_pds_split(doc, pds_rows):
	"""The rice of a PDS row comes in three PDS qualities, each with its own rate. The quantities of the three must add up to the
	Received Quantity, and a quality with a quantity must have a rate. The amount of the row is worked out from them (see install_trip_amount)."""
	quantities = [flt(doc.get(q)) for q in PDS_QTY_FIELDS]
	if any(q < 0 for q in quantities):
		frappe.throw(_("A PDS quantity cannot be negative."))
	doc.quality_pds_amount = pds_amount(doc, doc.precision("quality_pds_amount"))
	if not any(quantities):
		return
	if len(pds_rows) > 1:
		frappe.throw(_("Only one row of PDS Quality can be split into the three PDS qualities. Make a separate receipt for each PDS row."))
	for label, quantity, rate_field in zip(("1st", "2nd", "3rd"), quantities, PDS_RATE_FIELDS):
		if quantity and flt(doc.get(rate_field)) <= 0:
			frappe.throw(_("{0} Quality PDS Rate is required because a quantity is given for it.").format(label))
	received = flt(pds_rows[0].get("qty"))
	if flt(sum(quantities) - received, pds_rows[0].precision("qty")) != 0:
		frappe.throw(
			_("The three PDS quantities add up to {0}, but the Received Qty is {1}. Please make them equal.").format(
				flt(sum(quantities), pds_rows[0].precision("qty")), flt(received, pds_rows[0].precision("qty"))
			),
			title=_("PDS quantities do not match"),
		)


def require_pds_split_on_submit(doc, method=None):
	"""A PDS row cannot be submitted until its quantity is split into the three PDS qualities (otherwise it has no amount)."""
	for row in doc.get("items") or []:
		if PDS_QUALITY in (row.get("quality") or "") and flt(row.get("qty")) > 0 and not any(flt(doc.get(q)) for q in PDS_QTY_FIELDS):
			frappe.throw(
				_("Row {0}: enter the quantity of each PDS quality (1st, 2nd and 3rd) before submitting.").format(row.get("idx")),
				title=_("PDS quantities are required"),
			)


def require_actual_oil_on_submit(doc, method=None):
	"""A Rice Bran row cannot be submitted until the Actual Oil Percentage Received is entered (its amount depends on it)."""
	for row in doc.get("items") or []:
		if row.get("item_code") == BRAN_ITEM and flt(row.get("qty")) > 0 and flt(row.get("actual_oil_percentage")) <= 0:
			frappe.throw(
				_("Row {0}: enter the Actual Oil Percentage Received before submitting.").format(row.get("idx")),
				title=_("Actual Oil Percentage is required"),
			)


def deal_amount(doc):
	"""What the goods received would cost at the rates agreed in the Purchase Order (a Rice Bran row at its quoted Rate Per MT), less the same
	Hamali and Discount. The Final Amount of the receipt is compared with this, so only the price effects (oil, PDS grades, an edited Rate) show
	as a difference, and a part delivery is not compared with the whole order."""
	total = 0
	for row in doc.get("items") or []:
		qty = flt(row.get("qty"))
		if not row.get("purchase_order_item"):
			total += flt(row.get("amount"))
			continue
		rate = flt(row.get("po_rate")) or flt(frappe.db.get_value("Purchase Order Item", row.purchase_order_item, "rate"))
		if row.get("item_code") == BRAN_ITEM and flt(row.get("rate_per_mt")):
			tonnes = qty * flt(row.get("avg_wt")) if row.get("uom") == TRIP_UOM else qty / QUINTAL_PER_MT
			total += tonnes * flt(row.get("rate_per_mt"))
		elif PDS_QUALITY in (row.get("quality") or ""):
			total += flt(row.get("amount"))  # the rates of the PDS qualities are the order's; the amount is already grade by grade
		elif row.get("uom") == TRIP_UOM:
			total += qty * flt(row.get("avg_wt")) * QUINTAL_PER_MT * rate
		else:
			total += qty * rate
	return total_final_amount(total, doc.get("total_hamali"), doc.get("discount_amount"))


def set_deal_fields(doc):
	"""The Deal Amount for this receipt and the Difference (received minus deal)."""
	if not doc.get("purchase_order"):
		doc.deal_amount = doc.amount_difference = 0
		return
	doc.deal_amount = flt(deal_amount(doc), doc.precision("deal_amount"))
	doc.amount_difference = flt(flt(doc.get("total_final_amount")) - flt(doc.deal_amount), doc.precision("amount_difference"))


def link_purchase_order(doc):
	"""A receipt made with the Create button has no Purchase Order on top: take it from the Items when they all come from one order."""
	if doc.get("purchase_order"):
		return
	orders = {row.get("purchase_order") for row in doc.get("items") or [] if row.get("purchase_order")}
	if len(orders) == 1:
		doc.purchase_order = orders.pop()


PDS_PCT_FIELDS = ("quality_pds_pct_1", "quality_pds_pct_2", "quality_pds_pct_3")


def ordered_quantity(row):
	"""The Ordered Qty of a receipt or invoice row: its own field, else the quantity of the order row it was made from."""
	if flt(row.get("ordered_qty")):
		return flt(row.get("ordered_qty"))
	if row.get("purchase_order_item") or row.get("po_detail"):
		return flt(frappe.db.get_value("Purchase Order Item", row.get("purchase_order_item") or row.get("po_detail"), "qty"))
	if row.get("pr_detail"):
		return flt(frappe.db.get_value("Purchase Receipt Item", row.pr_detail, "ordered_qty"))
	return 0


def sync_pds_quantity(doc, method=None):
	"""The quantity of the PDS row is split into the three PDS qualities. The split is typed in Qtl, or (when the tick box is ticked) as a percentage of the Ordered Qty
	(then the three quantities are worked out here). The Received Quantity of the row is the sum of the three quantities (filled in here,
	so the staff do not type it twice). Runs before ERPNext works the totals out."""
	pds_rows = [row for row in doc.get("items") or [] if PDS_QUALITY in (row.get("quality") or "")]
	if doc.get("quality_pds_percentage") and len(pds_rows) == 1 and any(flt(doc.get(p)) for p in PDS_PCT_FIELDS):
		ordered = ordered_quantity(pds_rows[0])
		if not ordered:
			frappe.throw(_("A percentage of the Ordered Qty needs a Purchase Order. Choose the Purchase Order, or enter the quantities in Qtl."))
		if any(flt(doc.get(p)) < 0 for p in PDS_PCT_FIELDS):
			frappe.throw(_("A PDS percentage cannot be negative."))
		for quantity_field, pct_field in zip(PDS_QTY_FIELDS, PDS_PCT_FIELDS):
			doc.set(quantity_field, flt(ordered * flt(doc.get(pct_field)) / 100, pds_rows[0].precision("qty")))
	quantities = [flt(doc.get(q)) for q in PDS_QTY_FIELDS]
	if len(pds_rows) == 1 and any(quantities):
		row = pds_rows[0]
		row.qty = flt(sum(quantities), row.precision("qty"))
		row.received_qty = row.qty


def require_received_quantity(doc, method=None):
	"""A receipt made from an order starts with an empty Received Quantity: the staff must type what has really arrived, or remove the row."""
	for row in doc.get("items") or []:
		if row.get("purchase_order_item") and flt(row.get("qty")) <= 0:
			frappe.throw(
				_("Row {0}: enter the Received Qty after checking the goods, or remove the row if nothing has arrived.").format(row.get("idx")),
				title=_("Received Qty is required"),
			)


def validate_purchase_receipt(doc, method=None):
	align_cost_center_with_company(doc)  # a Cost Center that came from the order must belong to this receipt's Company
	apply_order_rules(doc)
	link_purchase_order(doc)
	statuses = []
	for row in doc.get("items") or []:
		if not row.get("purchase_order_item"):
			continue
		line = frappe.db.get_value("Purchase Order Item", row.purchase_order_item, ["qty", "received_qty"], as_dict=True)
		if not line:
			continue
		precision = row.precision("received_qty")
		row.ordered_qty = line.qty
		row.receipt_status = item_status(line.qty, line.received_qty, row.get("received_qty") or row.get("qty"), precision)
		statuses.append(row.receipt_status)
	doc.receipt_status = receipt_status(statuses)

	if doc.get("hamali_payer") == HAMALI_PAYING:
		doc.total_hamali = total_hamali(hamali_bags(doc.get("items")), doc.get("hamali_rate"), doc.precision("total_hamali"))
	else:
		doc.hamali_rate = 0
		doc.total_hamali = 0
	doc.total_final_amount = total_final_amount(doc.get("total"), doc.get("total_hamali"), doc.get("discount_amount"), doc.precision("total_final_amount"))
	set_deal_fields(doc)


def install_ordered_qty_on_receipt(*args, **kwargs):
	"""ERPNext fills a new Purchase Receipt row's quantity with what is still to come from the order. Here that quantity goes to
	Ordered Qty and the Received Quantity is left empty: the staff type it after checking how much has really arrived.
	This wraps the step that makes a receipt from an order (ERPNext is not edited), so the Create button and the Purchase Order field
	of the receipt both get it. Only rows without an Ordered Qty are changed, so rows already filled in are left alone.
	Safe to call any number of times; called by before_request and before_job (hooks.py)."""
	from erpnext.buying.doctype.purchase_order import purchase_order

	original = purchase_order.make_purchase_receipt
	if getattr(original, "_ivri_od_ordered_qty", None):
		return

	@functools.wraps(original)
	def make_purchase_receipt(source_name, target_doc=None, args=None):
		doc = original(source_name, target_doc, args)
		move_quantity_to_ordered(doc.get("items"))
		doc.purchase_order = doc.get("purchase_order") or source_name
		return doc

	make_purchase_receipt._ivri_od_ordered_qty = True
	make_purchase_receipt._ivri_od_original = original
	purchase_order.make_purchase_receipt = frappe.whitelist()(make_purchase_receipt)


def uninstall_ordered_qty_on_receipt():
	"""Put ERPNext's own step back (used by tests)."""
	from erpnext.buying.doctype.purchase_order import purchase_order

	step = purchase_order.make_purchase_receipt
	if getattr(step, "_ivri_od_ordered_qty", None):
		purchase_order.make_purchase_receipt = step._ivri_od_original


def move_quantity_to_ordered(rows):
	for row in rows or []:
		if row.get("ordered_qty") or not row.get("purchase_order_item"):
			continue
		line = frappe.db.get_value("Purchase Order Item", row.purchase_order_item, ["qty", "rate"], as_dict=True) or {}
		row.ordered_qty = flt(line.get("qty"))
		row.po_rate = flt(line.get("rate"))  # the rate of the order line, kept to show how the receipt differs from the deal
		for fieldname in ("qty", "received_qty", "stock_qty", "received_stock_qty", "amount", "base_amount", "net_amount", "base_net_amount"):
			if row.meta.get_field(fieldname):
				row.set(fieldname, 0)
