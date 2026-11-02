# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Government paddy receipt posting: GRN Note -> ERPNext Stock Entry (Material Receipt).

Rules:
- The quantity is GRN Note net_weight (QT = quintal), a copy of Weigh Bridge Measurement net_weight.
  Nothing is recalculated here: gross, tare, gunny, deduction and returned bags are not touched.
- Government procurement has no charges: every row is zero valuation, no rate is ever set.
- Posting is an explicit action (post_grn_to_stock) for Stock Manager. Settings are off by default.
- The receipt goes to the physical warehouse of the legal Company (one per physical location, shared by the Raw and
  Boiled units). The owning operating unit is kept on the Stock Entry, on the Batch (its id carries the unit) and on
  the Bag Ledger. A per-unit warehouse of the older setup is still accepted while it exists.
- One active posting per GRN Note: Stock Posting Log.active_key is unique.
- After posting, the GRN Note and its Weigh Bridge Measurement cannot change the posted values.
  A correction is: cancel the posting (cancel_stock_posting), fix the source, post again.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, now_datetime

from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	KG_PER_QUINTAL,
)
from ivri_od.procurement.inventory_foundation import batch_unit_column
from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name

POSTING_ROLES = ("Stock Manager", "System Manager")
ACCEPTED_DECISIONS = ("Accepted", "Partially Accepted")
QUINTAL = "Quintal"
KG = "Kg"
GOVERNMENT = "Government"

# Values copied to the Stock Posting Log when posting; the GRN Note / WBM may not change them afterwards.
QTY_PRECISION = 3


def convert_to_stock_qty(net_weight_qt, stock_uom: str) -> float:
	"""GRN net_weight is in quintal. Only convert when the Item's stock UOM is Kg."""
	qty = flt(net_weight_qt, QTY_PRECISION)
	if stock_uom == QUINTAL:
		return qty
	if stock_uom == KG:
		return flt(qty * KG_PER_QUINTAL, QTY_PRECISION)
	frappe.throw(_("Stock UOM {0} is not supported for paddy receipts. Use Quintal or Kg.").format(stock_uom))


def get_active_posting(grn_name: str, for_update: bool = False):
	"""The active posting of a GRN Note. for_update reads the latest committed row (a plain read can be a
	stale snapshot while another posting of the same GRN is committing)."""
	return frappe.db.get_value(
		"Stock Posting Log",
		{"grn_note": grn_name, "status": "Posted"},
		[
			"name", "stock_entry", "net_weight_qt", "pass_unique_key", "weigh_bridge_measurement",
			"mill_name", "qc_decision", "no_of_bags", "is_local_procurement",
		],
		as_dict=True,
		for_update=for_update,
	)


def snapshot_differences(grn, posting) -> list[str]:
	"""Protected GRN values that no longer match what was posted."""
	changes = []
	if flt(grn.get("net_weight"), QTY_PRECISION) != flt(posting.net_weight_qt, QTY_PRECISION):
		changes.append(_("Net Weight (QT): posted {0}, now {1}").format(posting.net_weight_qt, grn.get("net_weight")))
	for fieldname, label in (
		("pass_unique_key", "Pass Unique Key"),
		("weigh_bridge_measurement", "Weigh Bridge Measurement"),
		("mill_name", "Mill Name"),
		("qc_decision", "QC Decision"),
	):
		if (grn.get(fieldname) or "").strip() != (posting.get(fieldname) or "").strip():
			changes.append(_("{0} changed").format(_(label)))
	# Physical bags = GRN Note.total_bags (the packets counted at the Quality Check, carried by the Weigh Bridge).
	# GRN Note.no_of_bags is only the Transit Pass reference and is not part of the ledger. The Stock Posting Log
	# keeps the physical count in its existing "no_of_bags" column (no schema change).
	if cint(grn.get("total_bags")) != cint(posting.no_of_bags):
		changes.append(_("Physical bags (Total Bags): posted {0}, now {1}").format(posting.no_of_bags, grn.get("total_bags")))
	if cint(grn.get("is_local_procurement")) != cint(posting.is_local_procurement):
		changes.append(_("Local Procurement flag changed"))
	return changes


def government_pass_errors(grn, wbm) -> list[str]:
	"""A GRN Note is a government receipt only when its Pass Unique Key resolves to exactly one PPAS Transit Pass
	that agrees with it. Nothing else decides this (not the supplier, warehouse, Item or bag count). A populated
	but unresolved key fails safely."""
	key = (grn.get("pass_unique_key") or "").strip()
	if cint(grn.get("is_local_procurement")):
		if key:
			return [
				_("This GRN Note is marked as a Local Paddy Purchase but also carries Pass Unique Key {0}. It is inconsistent, so it is not posted.").format(key)
			]
		return [_("This is a local paddy purchase (no Pass Unique Key). Government paddy posting and its bag ledger do not apply.")]
	if not key:
		return [_("GRN Note has no Pass Unique Key, so it is not a government Transit Pass receipt.")]
	rows = grn.get("tp_rows")
	if rows is None:
		return [_("Pass Unique Key {0} could not be checked against the PPAS Transit Pass.").format(key)]
	errors = []
	if not rows:
		errors.append(_("Pass Unique Key {0} does not match any PPAS Transit Pass.").format(key))
	elif len(rows) > 1:
		errors.append(_("Pass Unique Key {0} matches {1} PPAS Transit Passes. It must match exactly one.").format(key, len(rows)))
	else:
		tp = rows[0]
		if (tp.get("pass_unique_key") or "").strip() != key:
			errors.append(_("Pass Unique Key {0} differs from the Transit Pass key {1}.").format(key, tp.get("pass_unique_key")))
		grn_tp_no = str(grn.get("transit_pass_no") or "").strip()
		if grn_tp_no and str(tp.get("transit_pass_no") or "").strip() != grn_tp_no:
			errors.append(
				_("GRN Note Transit Pass No {0} differs from the Transit Pass record ({1}).").format(grn_tp_no, tp.get("transit_pass_no"))
			)
	if wbm and (wbm.get("pass_unique_key") or "").strip() != key:
		errors.append(
			_("The Weigh Bridge Pass Unique Key ({0}) differs from the GRN Note's ({1}).").format(wbm.get("pass_unique_key") or "-", key)
		)
	return errors


def physical_bag_errors(grn, wbm) -> list[str]:
	"""The bag ledger counts PHYSICAL bags: GRN Note.total_bags. It must be verifiable, and it must belong to
	this load alone. Anything else is refused, never guessed."""
	errors = []
	physical = cint(grn.get("total_bags"))
	if physical <= 0:
		errors.append(_("No physical bags are counted on this GRN Note (Total Bags is 0)."))
	if cint(wbm.get("total_bags")) != physical:
		errors.append(
			_("GRN Note Total Bags ({0}) differs from the Weigh Bridge Total Bags ({1}). Re-save the Weigh Bridge first.").format(
				physical, cint(wbm.get("total_bags"))
			)
		)
	qc_bags = wbm.get("qc_received_bags")
	if qc_bags is None:
		errors.append(_("The Quality Check of this weighment was not found, so the counted bags cannot be verified."))
	else:
		if cint(qc_bags) != physical:
			errors.append(
				_("Quality Check Paddy Received (Bags) is {0} but the packet lines add up to {1}. Correct the Quality Check first.").format(
					cint(qc_bags), physical
				)
			)
		if cint(wbm.get("qc_returned_bags")) > 0:
			errors.append(
				_("Bags were returned at the Quality Check ({0}). The bags kept in stock are not established, so this cannot be posted.").format(
					cint(wbm.get("qc_returned_bags"))
				)
			)
	shared = wbm.get("shared_with") or []
	if shared:
		errors.append(
			_("The bags of this load are shared with {0}: they use the same Quality Check or vehicle visit, so the physical bags cannot be split between them. Posting is refused to avoid counting the same bags twice.").format(
				", ".join(shared)
			)
		)
	return errors


def unloading_point_errors(grn, warehouse_row) -> list[str]:
	"""When the Quality Check names a valid mapped warehouse as the Unloading Point, the receipt goes there.
	A legacy free-text value (not a warehouse) puts no constraint on the choice."""
	chosen = (warehouse_row or {}).get("name")
	named = (grn.get("unloading_warehouse") or "").strip()
	if named and chosen and chosen != named:
		return [
			_("The Quality Check says this load was unloaded at {0}. Post to that warehouse, or correct the Quality Check first.").format(named)
		]
	return []


def _unloading_warehouse(unloading_point: str) -> str:
	"""The Unloading Point as an enabled warehouse mapped to a physical location, else empty (legacy free text, blank, or unmapped)."""
	value = (unloading_point or "").strip()
	if not value:
		return ""
	return (
		frappe.db.get_value(
			"Warehouse",
			{"name": value, "physical_location": ["is", "set"], "is_group": 0, "disabled": 0},
			"name",
		)
		or ""
	)


def _loads_sharing_qc(qc_name: str, gate_entry: str, wbm_name: str, grn_name: str) -> list[str]:
	"""Other weighments or GRN Notes counted from the same Quality Check or the same vehicle visit (Gate Entry).
	One Quality Check exists per Gate Entry, so any other weighment on it carries the same bag count."""
	or_filters = [["quality_check", "=", qc_name]]
	if gate_entry:
		or_filters.append(["gate_entry", "=", gate_entry])
	shared = frappe.get_all(
		"Weigh Bridge Measurement", filters=[["name", "!=", wbm_name]], or_filters=or_filters, pluck="name"
	)
	shared += frappe.get_all(
		"GRN Note",
		filters={"quality_check": qc_name, "name": ["!=", grn_name], "docstatus": ["<", 2]},
		pluck="name",
	)
	return sorted(set(shared))


def _settings():
	return frappe.get_cached_doc("Stock Posting Settings")


def grn_posting_errors(grn, wbm, mill, item, warehouse_row) -> list[str]:
	"""Everything that blocks posting, as plain messages. Pure: no writes."""
	errors = government_pass_errors(grn, wbm)
	if (grn.get("qc_decision") or "").strip() not in ACCEPTED_DECISIONS:
		errors.append(_("QC Decision must be Accepted or Partially Accepted."))
	if not wbm:
		errors.append(_("Weigh Bridge Measurement not found for this GRN Note."))
	else:
		if (wbm.get("quality_test") or "").strip() not in ACCEPTED_DECISIONS:
			errors.append(_("Weigh Bridge quality test must be Accepted or Partially Accepted."))
		if not flt(wbm.get("tare_weight")):
			errors.append(_("Tare weight is not entered on the Weigh Bridge."))
		if flt(wbm.get("net_weight"), QTY_PRECISION) <= 0:
			errors.append(_("Weigh Bridge net weight is zero."))
		if flt(grn.get("net_weight"), QTY_PRECISION) != flt(wbm.get("net_weight"), QTY_PRECISION):
			errors.append(
				_("GRN Note net weight ({0}) differs from Weigh Bridge net weight ({1}). Re-save the Weigh Bridge first.").format(
					grn.get("net_weight"), wbm.get("net_weight")
				)
			)
		errors += physical_bag_errors(grn, wbm)
	if not mill:
		errors.append(_("The operating unit (Mill Master) could not be found from the Transit Pass."))
	else:
		if not cint(mill.get("is_active")):
			errors.append(_("Mill Master {0} is not active.").format(mill.get("name")))
		if not (mill.get("accounting_company") or "").strip():
			errors.append(
				_("Mill Master {0} has no Accounting Company yet. Set the legal Company first.").format(mill.get("name"))
			)
	if not item:
		errors.append(_("Select the Government Paddy Item in Stock Posting Settings."))
	else:
		if cint(item.get("disabled")) or not cint(item.get("is_stock_item")):
			errors.append(_("Government Paddy Item must be an enabled stock item."))
		if not cint(item.get("has_batch_no")):
			errors.append(_("Government Paddy Item must have batches enabled."))
		if item.get("stock_uom") not in (QUINTAL, KG):
			errors.append(_("Government Paddy Item stock UOM must be Quintal (or Kg)."))
	if not warehouse_row:
		errors.append(_("Warehouse not found."))
	else:
		if cint(warehouse_row.get("is_group")) or cint(warehouse_row.get("disabled")):
			errors.append(_("Warehouse must be an enabled, non-group warehouse."))
		if cint(warehouse_row.get("is_rejected_warehouse")):
			errors.append(_("Accepted paddy cannot go to a rejected-stock warehouse."))
		if mill and (warehouse_row.get("company") or "") != (mill.get("accounting_company") or ""):
			errors.append(_("Warehouse Company must be the Accounting Company of the operating unit."))
		if not ((warehouse_row.get("physical_location") or "").strip() or (warehouse_row.get("operating_unit") or "").strip()):
			errors.append(_("Warehouse is not mapped to a physical location."))
		elif mill and (warehouse_row.get("operating_unit") or "") not in ("", mill.get("name") or ""):
			errors.append(
				_("Warehouse belongs to operating unit {0}. Use the physical warehouse of the Company, or one of operating unit {1}.").format(
					warehouse_row.get("operating_unit"), mill.get("name")
				)
			)
		errors += unloading_point_errors(grn, warehouse_row)
	return errors


def _load_context(grn_name: str, warehouse: str):
	grn = frappe.get_doc("GRN Note", grn_name)
	wbm = (
		frappe.db.get_value(
			"Weigh Bridge Measurement",
			grn.weigh_bridge_measurement,
			["name", "quality_test", "tare_weight", "net_weight", "total_bags", "gate_entry", "pass_unique_key"],
			as_dict=True,
		)
		if grn.weigh_bridge_measurement
		else None
	)
	grn.unloading_warehouse = _unloading_warehouse(grn.unloading_point)
	pass_key = (grn.pass_unique_key or "").strip()
	grn.tp_rows = (
		frappe.get_all(
			"PPAS Transit Pass",
			filters={"pass_unique_key": pass_key},
			fields=["name", "pass_unique_key", "transit_pass_no"],
			limit_page_length=3,
		)
		if pass_key
		else []
	)
	if wbm:
		qc_name = (grn.quality_check or "").strip()
		qc = (
			frappe.db.get_value(
				"Quality Check", qc_name, ["paddy_received_in_pkt", "paddy_returned", "gate_entry"], as_dict=True
			)
			if qc_name
			else None
		)
		wbm.qc_received_bags = cint(qc.paddy_received_in_pkt) if qc else None
		wbm.qc_returned_bags = cint(qc.paddy_returned) if qc else 0
		wbm.shared_with = (
			_loads_sharing_qc(qc_name, (qc.gate_entry or wbm.gate_entry or "") if qc else "", wbm.name, grn.name)
			if qc_name
			else []
		)
	mill_name = resolve_mill_master_name(grn.pass_unique_key, grn.mill_name) if grn.pass_unique_key else ""
	mill = (
		frappe.db.get_value(
			"Mill Master", mill_name, ["name", "is_active", "accounting_company"], as_dict=True
		)
		if mill_name
		else None
	)
	settings = _settings()
	item = (
		frappe.db.get_value(
			"Item",
			settings.government_paddy_item,
			["name", "disabled", "is_stock_item", "has_batch_no", "stock_uom"],
			as_dict=True,
		)
		if settings.government_paddy_item
		else None
	)
	warehouse_row = frappe.db.get_value(
		"Warehouse",
		warehouse,
		["name", "company", "is_group", "disabled", "is_rejected_warehouse", "operating_unit", "physical_location"],
		as_dict=True,
	)
	return grn, wbm, mill, item, warehouse_row, settings


def _ensure_batch(item_code: str, season: str, grn, unit: str = "") -> str:
	"""One batch per season, quality and operating unit. The unit is part of the id, so Raw and Boiled paddy stay
	apart in a shared warehouse and the stock of each unit can be told by its batch."""
	quality = ((grn.get("paddy_quality") or "").strip() or "NA").upper()
	unit = (unit or "").strip()
	batch_id = f"{season}-GOV-{quality}" + (f"-{unit}" if unit else "")
	with_unit = bool(unit) and batch_unit_column()
	if frappe.db.exists("Batch", batch_id):
		fields = ["item", "season", "procurement_type"] + (["operating_unit"] if with_unit else [])
		batch = frappe.db.get_value("Batch", batch_id, fields, as_dict=True)
		if (
			batch.item != item_code
			or (batch.season or "") != season
			or (batch.procurement_type or "") != GOVERNMENT
			or (with_unit and (batch.operating_unit or "") != unit)
		):
			frappe.throw(_("Batch {0} exists but belongs to another item, season, procurement type or operating unit.").format(batch_id))
		return batch_id
	frappe.get_doc(
		{
			"doctype": "Batch",
			"batch_id": batch_id,
			"item": item_code,
			"season": season,
			"procurement_type": GOVERNMENT,
			"quality_grade": quality,
			"source_grn": grn.name,
			**({"operating_unit": unit} if with_unit else {}),
		}
	).insert()
	return batch_id


def _drift(grn, posting) -> list[str]:
	"""GRN values that changed since posting, plus the Weigh Bridge net weight and physical bag count themselves.
	The Weigh Bridge can be written without a GRN sync, so it is read here too."""
	changes = snapshot_differences(grn, posting)
	wbm = (grn.get("weigh_bridge_measurement") or "").strip()
	if wbm:
		row = frappe.db.get_value("Weigh Bridge Measurement", wbm, ["net_weight", "total_bags"], as_dict=True)
		if row and row.net_weight is not None and flt(row.net_weight, QTY_PRECISION) != flt(posting.net_weight_qt, QTY_PRECISION):
			changes.append(_("Weigh Bridge net weight: posted {0}, now {1}").format(posting.net_weight_qt, row.net_weight))
		if row and cint(row.total_bags) != cint(posting.no_of_bags):
			changes.append(_("Weigh Bridge Total Bags: posted {0}, now {1}").format(posting.no_of_bags, cint(row.total_bags)))
	return changes


@frappe.whitelist()
def get_stock_posting_status(grn_name: str) -> dict:
	"""For the GRN Note form: posted or not, who owns the stock, and any drift since posting."""
	frappe.has_permission("GRN Note", "read", throw=True)
	grn = frappe.get_doc("GRN Note", grn_name)
	posting = get_active_posting(grn_name)
	mill_name = resolve_mill_master_name(grn.pass_unique_key, grn.mill_name) if grn.pass_unique_key else ""
	company = (
		frappe.db.get_value("Mill Master", mill_name, "accounting_company") if mill_name else ""
	)
	return {
		"enabled": cint(_settings().enabled),
		"posted": bool(posting),
		"stock_entry": posting.stock_entry if posting else "",
		"drift": _drift(grn, posting) if posting else [],
		"operating_unit": mill_name or "",
		"unloading_warehouse": _unloading_warehouse(grn.unloading_point),
		"company": company or "",
		"is_local": cint(grn.is_local_procurement),
		"can_post": bool(set(frappe.get_roles()) & set(POSTING_ROLES)),
	}


@frappe.whitelist()
def post_grn_to_stock(grn_name: str, warehouse: str) -> str:
	"""Create and submit the Material Receipt for one GRN Note. Returns the Stock Entry name."""
	frappe.only_for(POSTING_ROLES)
	grn_name = (grn_name or "").strip()
	warehouse = (warehouse or "").strip()
	if not grn_name or not warehouse:
		frappe.throw(_("Select the GRN Note and the warehouse."))
	settings = _settings()
	if not cint(settings.enabled):
		frappe.throw(_("Government paddy stock posting is not enabled in Stock Posting Settings."))

	# Row lock: two clicks at once queue here, and the second sees the first posting.
	if not frappe.db.get_value("GRN Note", grn_name, "name", for_update=True):
		frappe.throw(_("GRN Note {0} not found.").format(grn_name))
	existing = get_active_posting(grn_name, for_update=True)
	if existing:
		frappe.throw(
			_("GRN Note {0} is already posted in Stock Entry {1}.").format(grn_name, existing.stock_entry),
			title=_("Already Posted"),
		)

	grn, wbm, mill, item, warehouse_row, settings = _load_context(grn_name, warehouse)
	errors = grn_posting_errors(grn, wbm, mill, item, warehouse_row)
	season = resolve_season_master_name(grn.cmr_season)
	if not season:
		errors.append(_("Season {0} of the Transit Pass is not in Season Master.").format(grn.cmr_season or "-"))
	if errors:
		frappe.throw("<br>".join(errors), title=_("Cannot Post to Stock"))

	stock_qty = convert_to_stock_qty(grn.net_weight, item.stock_uom)
	batch_no = _ensure_batch(item.name, season, grn, mill.name)
	posting_dt = get_datetime(grn.receipt_datetime) if grn.receipt_datetime else now_datetime()

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Receipt"
	se.purpose = "Material Receipt"
	se.company = mill.accounting_company
	se.set_posting_time = 1
	se.posting_date = posting_dt.date()
	se.posting_time = posting_dt.time().strftime("%H:%M:%S")
	se.to_warehouse = warehouse
	se.grn_note = grn.name
	se.weigh_bridge_measurement = grn.weigh_bridge_measurement
	se.pass_unique_key = grn.pass_unique_key
	se.ppc = grn.ppc
	se.transit_pass_no = grn.transit_pass_no
	se.operating_unit = mill.name
	se.append(
		"items",
		{
			"item_code": item.name,
			"qty": stock_qty,
			"uom": item.stock_uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": 1,
			"transfer_qty": stock_qty,
			"t_warehouse": warehouse,
			"basic_rate": 0,
			"allow_zero_valuation_rate": 1,
			"use_serial_batch_fields": 1,
			"batch_no": batch_no,
			"no_of_bags": cint(grn.total_bags),  # physical bags, not the Transit Pass count
		},
	)
	se.flags.from_grn_posting = True
	se.insert()
	se.submit()

	log = frappe.get_doc(
		{
			"doctype": "Stock Posting Log",
			"grn_note": grn.name,
			"active_key": grn.name,
			"status": "Posted",
			"stock_entry": se.name,
			"company": mill.accounting_company,
			"operating_unit": mill.name,
			"warehouse": warehouse,
			"item_code": item.name,
			"batch_no": batch_no,
			"season": season,
			"net_weight_qt": flt(grn.net_weight, QTY_PRECISION),
			"stock_qty": stock_qty,
			"stock_uom": item.stock_uom,
			"no_of_bags": cint(grn.total_bags),  # physical bags (existing column; see snapshot_differences)
			"pass_unique_key": grn.pass_unique_key,
			"weigh_bridge_measurement": grn.weigh_bridge_measurement,
			"mill_name": grn.mill_name,
			"qc_decision": grn.qc_decision,
			"is_local_procurement": cint(grn.is_local_procurement),
			"posted_by": frappe.session.user,
			"posted_on": now_datetime(),
		}
	)
	log.insert(ignore_permissions=True)
	return se.name


@frappe.whitelist()
def cancel_stock_posting(grn_name: str, reason: str) -> str:
	"""Cancel the posted Stock Entry of a GRN Note (frees the GRN Note for correction)."""
	frappe.only_for(POSTING_ROLES)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Enter the reason for cancelling the stock posting."))
	posting = get_active_posting((grn_name or "").strip())
	if not posting:
		frappe.throw(_("GRN Note {0} has no active stock posting.").format(grn_name))
	se = frappe.get_doc("Stock Entry", posting.stock_entry)
	se.flags.cancel_reason = reason
	se.cancel()  # negative stock / later use of the batch blocks this; on_cancel_stock_entry closes the log
	return posting.stock_entry


# ---- doc_events (hooks.py) ----


def validate_stock_entry(doc, method=None):
	"""A Stock Entry linked to a GRN Note must come from the posting action and carry no charge."""
	if not (doc.get("grn_note") or "").strip():
		return
	if not doc.flags.get("from_grn_posting"):
		frappe.throw(_("Use Post to Stock on the GRN Note. A receipt linked to a GRN cannot be made by hand."))
	if doc.purpose != "Material Receipt":
		frappe.throw(_("Only a Material Receipt can be linked to a GRN Note."))
	total = 0.0
	bags = 0
	for row in doc.items:
		bags += cint(row.get("no_of_bags"))
		if row.s_warehouse or not row.t_warehouse:
			frappe.throw(_("Row {0}: a government paddy receipt only has a target warehouse.").format(row.idx))
		if not cint(row.allow_zero_valuation_rate) or flt(row.basic_rate):
			frappe.throw(_("Row {0}: government paddy has no procurement charge. No rate is allowed.").format(row.idx))
		total += flt(row.transfer_qty)
	grn_row = frappe.db.get_value("GRN Note", doc.grn_note, ["net_weight", "total_bags"], as_dict=True)
	stock_uom = doc.items[0].stock_uom if doc.items else QUINTAL
	if flt(total, QTY_PRECISION) != convert_to_stock_qty(grn_row.net_weight, stock_uom):
		frappe.throw(_("Receipt quantity must equal the GRN Note net weight."))
	if bags != cint(grn_row.total_bags):
		frappe.throw(_("Receipt bags must equal the GRN Note Total Bags (the physical count), not the Transit Pass bags."))


def on_cancel_stock_entry(doc, method=None):
	"""Closing the posting log when its Stock Entry is cancelled (also from the Stock Entry screen)."""
	if not (doc.get("grn_note") or "").strip():
		return
	log_name = frappe.db.get_value(
		"Stock Posting Log", {"stock_entry": doc.name, "status": "Posted"}, "name"
	)
	if not log_name:
		return
	frappe.db.set_value(
		"Stock Posting Log",
		log_name,
		{
			"status": "Cancelled",
			"active_key": None,
			"cancelled_by": frappe.session.user,
			"cancelled_on": now_datetime(),
			"cancel_reason": doc.flags.get("cancel_reason") or _("Cancelled from the Stock Entry"),
		},
	)


def guard_grn_note(doc, method=None):
	"""After posting, the protected GRN values cannot change. Runs on_update because the WBM sync
	saves the GRN with ignore_validate, which would skip a validate hook."""
	posting = get_active_posting(doc.name)
	if not posting:
		return
	changes = snapshot_differences(doc, posting)
	if changes:
		frappe.throw(
			_("GRN Note {0} is posted in Stock Entry {1}. Cancel the posting first, then correct and post again.").format(
				doc.name, posting.stock_entry
			)
			+ "<br>"
			+ "<br>".join(changes),
			title=_("Posted Receipt Is Frozen"),
		)


def guard_grn_note_trash(doc, method=None):
	posting = get_active_posting(doc.name)
	if posting:
		frappe.throw(
			_("GRN Note {0} is posted in Stock Entry {1} and cannot be deleted.").format(doc.name, posting.stock_entry)
		)


def guard_weigh_bridge(doc, method=None):
	"""The Weigh Bridge net weight and physical bag count of a posted GRN cannot change."""
	grn_name = frappe.db.get_value(
		"GRN Note", {"weigh_bridge_measurement": doc.name, "docstatus": ["<", 2]}, "name"
	)
	posting = get_active_posting(grn_name) if grn_name else None
	if posting and (
		flt(doc.net_weight, QTY_PRECISION) != flt(posting.net_weight_qt, QTY_PRECISION)
		or cint(doc.get("total_bags")) != cint(posting.no_of_bags)
	):
		frappe.throw(
			_("The GRN Note {0} of this weighment is posted in Stock Entry {1}. Cancel the posting before changing the net weight or the bags.").format(
				grn_name, posting.stock_entry
			),
			title=_("Posted Receipt Is Frozen"),
		)


def guard_weigh_bridge_trash(doc, method=None):
	grn_name = frappe.db.get_value(
		"GRN Note", {"weigh_bridge_measurement": doc.name, "docstatus": ["<", 2]}, "name"
	)
	posting = get_active_posting(grn_name) if grn_name else None
	if posting:
		frappe.throw(
			_("This weighment feeds GRN Note {0}, posted in Stock Entry {1}. It cannot be deleted.").format(
				grn_name, posting.stock_entry
			)
		)


def validate_warehouse(doc, method=None):
	"""A warehouse mapped to a physical location. The legal Company owns the stock accounting-wise.

	- SHARED warehouse (the standard): a physical location and no operating unit. One per physical location and
	  Company, used by the Raw and the Boiled units alike. The unit that owns stock in it is kept on the batch.
	- per-unit warehouse (the older setup, until retired): an operating unit and a physical location. The unit's
	  Accounting Company (when set) must be the warehouse Company, and one warehouse per (unit, location).
	- in both: the physical location is required, active, and of the same Company unless it is marked as shared.
	"""
	unit = (doc.get("operating_unit") or "").strip()
	location = (doc.get("physical_location") or "").strip()
	if not unit and not location:
		return  # not an inventory warehouse: leave it alone
	if unit:
		if not frappe.db.exists("Mill Master", unit):
			frappe.throw(_("Operating unit {0} not found.").format(unit))
		company = frappe.db.get_value("Mill Master", unit, "accounting_company")
		if company and company != doc.company:
			frappe.throw(
				_("Operating unit {0} belongs to {1}. The warehouse Company must match.").format(unit, company)
			)
	if cint(doc.get("is_group")):
		return
	if not location:
		frappe.throw(_("Select the Physical Location of this warehouse."))
	place = frappe.db.get_value(
		"Physical Location", location, ["company", "is_active", "shared_with_other_companies"], as_dict=True
	)
	if not place:
		frappe.throw(_("Physical Location {0} not found.").format(location))
	if not cint(place.is_active):
		frappe.throw(_("Physical Location {0} is not active.").format(location))
	if place.company != doc.company and not cint(place.shared_with_other_companies):
		frappe.throw(
			_("Physical Location {0} belongs to {1}. Mark it as holding stock of other Companies first.").format(
				location, place.company
			)
		)
	if cint(doc.get("disabled")):
		return
	filters = {"physical_location": location, "is_group": 0, "disabled": 0, "name": ["!=", doc.name or ""]}
	if unit:
		clash = frappe.db.get_value("Warehouse", {**filters, "operating_unit": unit}, "name")
		if clash:
			frappe.throw(
				_("Warehouse {0} already holds stock of {1} in {2}. One warehouse per owner and place.").format(
					clash, unit, location
				)
			)
		return
	clash = frappe.db.get_value(
		"Warehouse", {**filters, "operating_unit": ["is", "not set"], "company": doc.company}, "name"
	)
	if clash:
		frappe.throw(
			_("Warehouse {0} is already the shared warehouse of {1} for {2}. One warehouse per physical location.").format(
				clash, location, doc.company
			)
		)
