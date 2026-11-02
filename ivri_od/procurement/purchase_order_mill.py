# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Rice mill fields on the standard Purchase Order.

The Hamali section is shown, and Hamali Paying is required, only while an Items row has the UOM Bags (or Nos, on older orders).
Hamali is worked out only when Hamali Paying is Yes: Total Hamali is the bags times the Hamali Rate (both are zero for No). The bags are the quantity of the Items rows whose UOM is Bags (or Nos, on older orders).
Each Items row has a Quality and a Dimension whose choices depend on its Item (ITEM_RULES).
Total Final Amount is Total (INR) minus Total Hamali minus the Additional Discount Amount.
A row whose UOM is Trip has an Avg Wt(MT) (25 unless changed, in metric tonnes) and its Amount is Quantity x Avg Wt(MT) x 10 x Rate, because the Rate is per quintal and 1 MT is 10 quintal (see install_trip_amount).
The Additional Discount section is shown, and a discount kept, only for the Payment Mode Cash.
The Company need not be filled: an empty one becomes the default Company before saving.
Location Name is required for an X-location delivery. Transport details are required only for a Transport Vehicle
and are cleared for an Owned Vehicle. Hamali and freight are for information: they are not added to the taxes,
totals or accounts.
"""

import frappe
from frappe import _
from frappe.utils import flt

BAG_UOMS = ("Bags", "Nos")  # Nos is kept for orders made before Bags was added
ALLOWED_UOMS = ("Bags", "Trip", "Quintal")
# Quality and Dimension choices of an Items row by Item Code. An Item without an entry (or with an empty list) has no such field.
# Keep in step with ITEM_RULES in public/js/purchase_order_mill.js and the "depends on" of the two Purchase Order Item fields.
ITEM_RULES = {
	"BOILED-RICE": {"quality": ["Fresh Milling", "Lot Delivery", "PDS"], "dimension": []},
	"BIOMASS-PELLET": {"quality": ["Rice Husk", "Saw Dust", "Mix"], "dimension": ["8mm", "10mm", "16mm"]},
	"BIOMASS-BRIQUETTE": {"quality": ["Rice Husk", "Saw Dust", "Mix"], "dimension": ["90mm"]},
	"RAW-RICE": {
		"quality": [
			"25% Broken Fresh Milling",
			"10% Broken Fresh Milling",
			"25% Broken Lot Delivery",
			"10% Broken Lot Delivery",
			"25% Broken PDS",
			"10% Broken PDS",
		],
		"dimension": [],
	},
	"RICE-BRAN": {"quality": ["Boiled", "Raw", "Muri", "Silky"], "dimension": []},
	"REJECTION": {"quality": ["Boiled", "Raw", "Muri"], "dimension": []},
	"HUSK": {"quality": [], "dimension": []},
	"ASH": {"quality": [], "dimension": []},
}
DEFAULT_DIMENSION = {"BIOMASS-BRIQUETTE": "90mm"}
TRIP_UOM = "Trip"
QUINTAL_PER_MT = 10  # the Avg Wt is entered in MT but the Rate is per quintal; keep in step with QUINTAL_PER_MT in purchase_order_mill.js
DEFAULT_AVG_WT = 25  # keep in step with the default of the Avg Wt field and DEFAULT_AVG_WT in purchase_order_mill.js
PDS_QUALITY = "PDS"  # a Quality containing this (PDS, 25% / 10% Broken PDS) shows the three Quality PDS Rate fields
PDS_RATE_FIELDS = ("quality_pds_rate_1", "quality_pds_rate_2", "quality_pds_rate_3")
DISCOUNT_PAYMENT_MODE = "Cash"  # the Payment Mode that shows the Additional Discount section
DUST_ITEM = "PADDY"  # the Dust field is shown and kept only when an Item row is this
GUNNY_ITEMS = ("BOILED-RICE", "RAW-RICE", "MURI-RICE", "PADDY")  # the Gunny field is shown and kept only when an Item row is one of these
DEFAULT_COMPANY = "Laddu Gopal Industries"  # filled in when the Company is left empty (the form does not require it)
HAMALI_PAYING = "Yes"  # the value of Hamali Paying that switches the hamali rate and total on
RULE_DOCTYPES = ("Purchase Order", "Purchase Receipt", "Purchase Invoice")  # the documents that follow the Trip amount and the typed-in Rate rules
PAID_BY_QUALITY_DOCTYPES = ("Purchase Receipt", "Purchase Invoice")  # the documents whose Rice Bran and PDS rows are paid on the oil and the PDS qualities actually received
X_LOCATION = "X-location"
TRANSPORT_VEHICLE = "Transport Vehicle"
# For now only the Vehicle Ownership is asked: the transport fields are hidden and not required. Set this to True (and show
# the four fields again: Transporter, Vehicle Number, Driver, Freight Charges) to ask for the transport details again.
ASK_TRANSPORT_DETAILS = False
TRANSPORT_FIELDS = (
	("transporter", "Transporter"),
	("vehicle_number", "Vehicle Number"),
	("driver", "Driver"),
)
NON_NEGATIVE = (
	("hamali_rate", "Hamali Rate"),
	("freight_charges", "Freight Charges"),
)


def hamali_bags(items):
	"""Bags for hamali: the quantity of the Items rows whose UOM is Bags (or Nos)."""
	return sum(flt(row.get("qty")) for row in items or [] if row.get("uom") in BAG_UOMS)


def total_hamali(bags, rate, precision=None):
	"""Total hamali = bags x rate."""
	return flt(flt(bags) * flt(rate), precision)


def validate_item_uoms(doc):
	"""Items may use only Bags, Trip or Quintal. Rows already saved with another UOM are left as they are."""
	before = doc.get_doc_before_save()
	saved = {row.get("name"): row.get("uom") for row in before.get("items")} if before else {}
	for row in doc.get("items") or []:
		if row.get("uom") not in ALLOWED_UOMS and saved.get(row.get("name")) != row.get("uom"):
			frappe.throw(
				_("Row {0}: UOM must be Bags, Trip or Quintal.").format(row.get("idx")), title=_("Invalid UOM")
			)


def trip_amount(qty, avg_wt, rate, precision=None):
	"""Amount of a Trip row = Quantity x Avg Wt (MT) x 10 x Rate (per quintal)."""
	return flt(flt(qty) * flt(avg_wt) * QUINTAL_PER_MT * flt(rate), precision)


BRAN_ITEM = "RICE-BRAN"
BRAN_OIL_DEFAULT = {"Boiled": 25, "Muri": 25, "Raw": 22}  # the benchmark Oil Percentage a bran row starts with (the user can change it)
BRAN_UOMS = ("Quintal", "Trip")  # Rate Per MT works with these UOMs: 1 MT is 10 quintal
BRAN_FIELDS = ("rate_per_mt", "oil_percentage", "actual_oil_percentage", "oil_rate_per_mt")


def oil_adjusted_rate(rate_per_mt, benchmark, actual):
	"""Oil-adjusted rate per MT = (Quoted rate per MT / Benchmark oil %) x Actual oil %."""
	return flt(rate_per_mt) * flt(actual) / flt(benchmark) if flt(benchmark) else 0


def bran_oil_row(doc, row):
	"""True for a Purchase Receipt row of Rice Bran whose Actual Oil Percentage is known, so its rate is the oil-adjusted one."""
	return (
		doc.get("doctype") in PAID_BY_QUALITY_DOCTYPES
		and row.get("item_code") == BRAN_ITEM
		and row.get("uom") in BRAN_UOMS
		and flt(row.get("rate_per_mt")) > 0
		and flt(row.get("oil_percentage")) > 0
		and flt(row.get("actual_oil_percentage")) > 0
	)


def bran_amount(row):
	"""Amount of a Rice Bran receipt row = quantity in MT x oil-adjusted rate per MT (a Trip is Quantity x Avg Wt in MT)."""
	adjusted = oil_adjusted_rate(row.get("rate_per_mt"), row.get("oil_percentage"), row.get("actual_oil_percentage"))
	tonnes = flt(row.get("qty")) * flt(row.get("avg_wt")) if row.get("uom") == TRIP_UOM else flt(row.get("qty")) / QUINTAL_PER_MT
	return flt(tonnes * adjusted, row.precision("amount"))


def _has_field(row, fieldname):
	meta = getattr(row, "meta", None)
	return meta.get_field(fieldname) if meta else True


def apply_bran_rate(doc, method=None):
	"""Rice Bran rows (Purchase Order and Purchase Receipt): the quoted Rate Per MT gives the Rate (per quintal = per MT / 10), the
	benchmark Oil Percentage starts at 25 (Boiled, Muri) or 22 (Raw), and on the receipt the Actual Oil Percentage Received gives the
	oil-adjusted rate. The quoted Rate Per MT is never overwritten. Other Items keep none of these fields."""
	for row in doc.get("items") or []:
		if row.get("item_code") != BRAN_ITEM:
			for fieldname in BRAN_FIELDS:
				if _has_field(row, fieldname):
					row.set(fieldname, 0)
			continue
		if not flt(row.get("oil_percentage")) and BRAN_OIL_DEFAULT.get(row.get("quality")):
			row.oil_percentage = BRAN_OIL_DEFAULT[row.quality]
		label = frappe.bold(BRAN_ITEM)
		if flt(row.get("rate_per_mt")) <= 0:
			frappe.throw(_("Row {0}: Rate Per MT is required for {1}.").format(row.get("idx"), label))
		if row.get("uom") not in BRAN_UOMS:
			frappe.throw(_("Row {0}: for {1} the UOM must be Quintal or Trip, because the Rate is given per MT.").format(row.get("idx"), label))
		for fieldname, title in (("oil_percentage", "Oil Percentage"), ("actual_oil_percentage", "Actual Oil Percentage Received")):
			if _has_field(row, fieldname) and not 0 <= flt(row.get(fieldname)) <= 100:
				frappe.throw(_("Row {0}: {1} must be between 0 and 100.").format(row.get("idx"), _(title)))
		rate_per_mt = flt(row.rate_per_mt)
		if bran_oil_row(doc, row):
			rate_per_mt = oil_adjusted_rate(row.rate_per_mt, row.oil_percentage, row.actual_oil_percentage)
			row.oil_rate_per_mt = flt(rate_per_mt, 2)
			if flt(row.actual_oil_percentage) > flt(row.oil_percentage):
				frappe.msgprint(
					_("Row {0}: the Actual Oil Percentage is higher than the benchmark, so the oil-adjusted rate is higher than the quoted rate.").format(row.get("idx")),
					indicator="orange",
					alert=True,
				)
		elif _has_field(row, "oil_rate_per_mt"):
			row.oil_rate_per_mt = 0
		row.rate = flt(rate_per_mt / QUINTAL_PER_MT, row.precision("rate"))


PDS_QTY_FIELDS = ("quality_pds_qty_1", "quality_pds_qty_2", "quality_pds_qty_3")


def pds_amount(doc, precision=None):
	"""Amount of a PDS row on a receipt = the sum of quantity x rate of the three PDS qualities."""
	return flt(sum(flt(doc.get(q)) * flt(doc.get(r)) for q, r in zip(PDS_QTY_FIELDS, PDS_RATE_FIELDS)), precision)


def pds_split_row(doc):
	"""The one PDS row of a Purchase Receipt whose quantity has been split into the three PDS qualities, else None."""
	if doc.get("doctype") not in PAID_BY_QUALITY_DOCTYPES or not any(flt(doc.get(q)) for q in PDS_QTY_FIELDS):
		return None
	rows = [row for row in doc.get("items") or [] if PDS_QUALITY in (row.get("quality") or "")]
	return rows[0] if len(rows) == 1 else None


def install_trip_amount(*args, **kwargs):
	"""ERPNext works every Amount out as Quantity x Rate. This wraps that step (ERPNext is not edited) so a Purchase Order row
	whose UOM is Trip gets Quantity x Avg Wt(MT) x 10 x Rate (per quintal) instead. Safe to call any number of times; called by before_request,
	before_job and the Purchase Order's before_validate (hooks.py)."""
	from erpnext.controllers import taxes_and_totals

	calculator = taxes_and_totals.calculate_taxes_and_totals
	if getattr(calculator, "_ivri_od_trip_amount", None):
		return
	original = calculator.calculate_item_values

	def calculate_item_values(self):
		original(self)
		if self.doc.get("doctype") not in RULE_DOCTYPES or self.doc.get("is_consolidated") or self.discount_amount_applied:
			return
		for item in self.doc.items:
			if item.get("uom") == TRIP_UOM:
				item.amount = trip_amount(item.qty, item.get("avg_wt"), item.rate, item.precision("amount"))
				item.net_amount = item.amount
				self._set_in_company_currency(item, ["amount", "net_amount"])
		# a Rice Bran row of a receipt is paid on the oil-adjusted rate per MT
		for item in self.doc.items:
			if bran_oil_row(self.doc, item):
				item.amount = bran_amount(item)
				item.net_amount = item.amount
				item.net_rate = item.rate
				self._set_in_company_currency(item, ["rate", "net_rate", "amount", "net_amount"])
		# a receipt's PDS row is paid grade by grade (quantity x rate of each of the three PDS qualities)
		row = pds_split_row(self.doc)
		if row:
			row.amount = pds_amount(self.doc, row.precision("amount"))
			row.net_amount = row.amount
			row.rate = row.net_rate = flt(row.amount / flt(row.qty), row.precision("rate")) if flt(row.qty) else 0
			self._set_in_company_currency(row, ["rate", "net_rate", "amount", "net_amount"])

	calculator._ivri_od_original_item_values = original
	calculator.calculate_item_values = calculate_item_values
	calculator._ivri_od_trip_amount = True


def uninstall_trip_amount():
	"""Put ERPNext's own step back (used by tests)."""
	from erpnext.controllers import taxes_and_totals

	calculator = taxes_and_totals.calculate_taxes_and_totals
	if getattr(calculator, "_ivri_od_trip_amount", None):
		calculator.calculate_item_values = calculator._ivri_od_original_item_values
		calculator._ivri_od_trip_amount = False


def install_no_auto_rate(*args, **kwargs):
	"""ERPNext fills a row's Rate from the Item Price (or the last purchase) when the Item, UOM or Quantity changes. On a Purchase
	Order the user must type the Rate, so this wraps that lookup (ERPNext is not edited) to find no price for a Purchase Order row.
	Safe to call any number of times; called by before_request and before_job (hooks.py)."""
	from erpnext.stock import get_item_details

	lookup = get_item_details.get_price_list_rate
	if getattr(lookup, "_ivri_od_no_auto_rate", None):
		return

	def get_price_list_rate(ctx, item_doc, out=None):
		if (ctx.get("parenttype") or ctx.get("doctype")) in RULE_DOCTYPES:
			return out if out is not None else get_item_details.ItemDetails()
		return lookup(ctx, item_doc, out)

	get_price_list_rate._ivri_od_no_auto_rate = True
	get_price_list_rate._ivri_od_original = lookup
	get_item_details.get_price_list_rate = get_price_list_rate


def uninstall_no_auto_rate():
	"""Put ERPNext's own lookup back (used by tests)."""
	from erpnext.stock import get_item_details

	lookup = get_item_details.get_price_list_rate
	if getattr(lookup, "_ivri_od_no_auto_rate", None):
		get_item_details.get_price_list_rate = lookup._ivri_od_original


def install_no_warehouse_check(*args, **kwargs):
	"""ERPNext refuses a Purchase Order row of a stock Item that has no Warehouse. The Warehouse is not asked on a Purchase Order (it is
	given on the Purchase Receipt), so this wraps that check (ERPNext is not edited) to let a Purchase Order row pass.
	Safe to call any number of times; called by before_request and before_job (hooks.py)."""
	from erpnext.buying import utils

	check = utils.validate_stock_item_warehouse
	if getattr(check, "_ivri_od_no_warehouse_check", None):
		return

	def validate_stock_item_warehouse(row, item) -> None:
		if row.get("parenttype") == "Purchase Order":
			return
		return check(row, item)

	validate_stock_item_warehouse._ivri_od_no_warehouse_check = True
	validate_stock_item_warehouse._ivri_od_original = check
	utils.validate_stock_item_warehouse = validate_stock_item_warehouse


def uninstall_no_warehouse_check():
	"""Put ERPNext's own check back (used by tests)."""
	from erpnext.buying import utils

	check = utils.validate_stock_item_warehouse
	if getattr(check, "_ivri_od_no_warehouse_check", None):
		utils.validate_stock_item_warehouse = check._ivri_od_original


def validate_trip_avg_wt(doc):
	"""A Trip row needs an Avg Wt(MT) above zero (it is part of the Amount)."""
	for row in doc.get("items") or []:
		if row.get("uom") == TRIP_UOM and flt(row.get("avg_wt")) <= 0:
			frappe.throw(_("Row {0}: Avg Wt(MT) must be more than 0 when the UOM is Trip.").format(row.get("idx")))


def set_default_company(doc, method=None):
	"""Company is not asked on the form, but ERPNext cannot work out the Items without one: use the default Company."""
	if doc.get("company"):
		return
	company = DEFAULT_COMPANY if frappe.db.exists("Company", DEFAULT_COMPANY) else frappe.defaults.get_global_default("company")
	if company:
		doc.company = company


def align_cost_center_with_company(doc, method=None):
	"""The Cost Center (and each row's) is filled from the first Company. When the user picks another Company the old one stays
	behind and ERPNext refuses to save ("Cost Center does not belong to the Company"). Put the Company's own default back."""
	if not doc.get("company"):
		return
	default = frappe.get_cached_value("Company", doc.company, "cost_center")
	if not default:
		return
	for target in [doc, *(doc.get("items") or [])]:
		center = target.get("cost_center")
		if center and frappe.get_cached_value("Cost Center", center, "company") != doc.company:
			target.cost_center = default


def clear_discount_unless_cash(doc, method=None):
	"""The Additional Discount section is shown only for the Payment Mode Cash. For another mode an old discount must not stay
	behind (it would still change the totals while hidden). This runs before ERPNext works the totals out."""
	if doc.get("payment_mode") != DISCOUNT_PAYMENT_MODE:
		doc.discount_amount = 0
		doc.additional_discount_percentage = 0


def total_final_amount(total, hamali, discount=0, precision=None):
	"""Total Final Amount = Total (INR) - Total Hamali - Additional Discount Amount."""
	return flt(flt(total) - flt(hamali) - flt(discount), precision)


def validate_item_quality_dimension(doc):
	"""Quality and Dimension are required when the row's Item has choices, and must be one of them. A row whose Item has none keeps them empty."""
	for row in doc.get("items") or []:
		rule = ITEM_RULES.get(row.get("item_code"), {})
		for fieldname, label in (("quality", "Quality"), ("dimension", "Dimension(mm)")):
			choices = rule.get(fieldname, [])
			value = (row.get(fieldname) or "").strip()
			if not choices:
				if row.get(fieldname):
					row.set(fieldname, None)
			elif not value and fieldname == "dimension" and row.get("item_code") in DEFAULT_DIMENSION:
				row.set(fieldname, DEFAULT_DIMENSION[row.get("item_code")])
			elif not value:
				# the form requires the field when it is shown; the server holds the same rule for imports and the API
				frappe.throw(
					_("Row {0}: {1} is required for {2}.").format(row.get("idx"), _(label), frappe.bold(row.get("item_code"))),
					title=_("Missing {0}").format(_(label)),
				)
			elif value not in choices:
				frappe.throw(
					_("Row {0}: {1} must be one of {2}.").format(row.get("idx"), _(label), ", ".join(choices)),
					title=_("Invalid {0}").format(_(label)),
				)


def validate_item_rate(doc):
	"""The Rate must be entered (more than 0) on every row, except a row whose Quality is PDS (also 25% / 10% Broken PDS)."""
	for row in doc.get("items") or []:
		if PDS_QUALITY in (row.get("quality") or "") or row.get("is_free_item"):
			continue
		if flt(row.get("rate")) <= 0:
			frappe.throw(_("Row {0}: Rate is required (only a PDS Quality can be left without a Rate).").format(row.get("idx")))


def validate_purchase_order(doc, method=None):
	validate_item_uoms(doc)
	validate_item_quality_dimension(doc)
	validate_trip_avg_wt(doc)
	validate_item_rate(doc)
	if any(row.get("uom") == TRIP_UOM for row in doc.get("items") or []) or not any(row.get("item_code") in GUNNY_ITEMS for row in doc.get("items") or []):
		doc.gunny_condition = ""  # Gunny is not asked for a Trip, nor for an Item other than Boiled Rice, Raw Rice, Muri Rice and Paddy
	if not any(PDS_QUALITY in (row.get("quality") or "") for row in doc.get("items") or []):
		for fieldname in PDS_RATE_FIELDS:
			doc.set(fieldname, 0)  # the PDS rates are asked only while a row's Quality is PDS
	if not any(row.get("item_code") == DUST_ITEM for row in doc.get("items") or []):
		doc.dust_condition = ""  # Dust is asked only for Paddy
	for fieldname, label in NON_NEGATIVE:
		if flt(doc.get(fieldname)) < 0:
			frappe.throw(_("{0} cannot be negative.").format(_(label)))

	if not any(row.get("uom") in BAG_UOMS for row in doc.get("items") or []):
		doc.hamali_payer = ""  # no Bags row: the Hamali section is hidden, so nothing may stay behind
	elif not doc.get("hamali_payer"):
		frappe.throw(_("Hamali Paying is required when the UOM is Bags."))
	if doc.get("hamali_payer") == HAMALI_PAYING:
		doc.total_hamali = total_hamali(hamali_bags(doc.get("items")), doc.get("hamali_rate"), doc.precision("total_hamali"))
	else:
		# Hamali Paying is No (or empty): there is no hamali, so an old rate or total must not stay behind
		doc.hamali_rate = 0
		doc.total_hamali = 0

	doc.total_final_amount = total_final_amount(
		doc.get("total"), doc.get("total_hamali"), doc.get("discount_amount"), doc.precision("total_final_amount")
	)

	if doc.get("delivery_type") == X_LOCATION:
		if not (doc.get("location_name") or "").strip():
			frappe.throw(_("Location Name is required when Delivery Type is X-location."))
		doc.location_name = doc.location_name.strip()
	else:
		doc.location_name = None

	if doc.get("vehicle_ownership") == TRANSPORT_VEHICLE:
		if ASK_TRANSPORT_DETAILS:
			validate_transport_details(doc)
	else:
		# an Owned Vehicle (or none) has no transporter, so old transport details must not stay behind
		for fieldname, _label in TRANSPORT_FIELDS:
			doc.set(fieldname, None)
		doc.freight_charges = 0


def validate_transport_details(doc):
	"""A Transport Vehicle needs its Transporter, Vehicle Number, Driver and Freight Charges."""
	for fieldname, label in TRANSPORT_FIELDS:
		if not (doc.get(fieldname) or "").strip():
			frappe.throw(_("{0} is required when Vehicle Ownership is Transport Vehicle.").format(_(label)))
	if flt(doc.get("freight_charges")) <= 0:
		frappe.throw(_("Freight Charges is required when Vehicle Ownership is Transport Vehicle."))
	if not frappe.db.get_value("Supplier", doc.transporter, "is_transporter"):
		frappe.throw(_("{0} is not marked as a Transporter in Supplier.").format(frappe.bold(doc.transporter)))
	doc.vehicle_number = doc.vehicle_number.strip().upper()
