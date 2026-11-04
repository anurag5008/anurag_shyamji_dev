# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Inventory foundation rules for the rice mills.

Two separate ideas, never mixed:
- OWNER of stock = operating unit (Mill Master) under a legal Company. Carried by the Warehouse
  (custom field operating_unit).
- PLACE of stock = Physical Location (nine sites). Carried by the Warehouse (physical_location).
One physical location = one Warehouse under its legal Company. Raw and Boiled units share it: such a SHARED
warehouse has a physical location and no operating unit. The operating unit that owns the stock is kept on the
Batch (Batch Operating Unit, part of the batch id), on the Stock Entry (Operating Unit) and on the Bag Ledger,
so the stock and the bags of every unit stay separate and the legal Company stays the accounting owner.
Older per-unit warehouses (one per operating unit and location) are still understood until they are retired;
the Stock by Physical Location report shows owner-wise balances and the combined total for both.

Rules enforced here (on Stock Entry, Warehouse and Mill Master), only for warehouses that are linked
to an operating unit, so nothing else in ERPNext is touched:
- Physical Transfer: owner unchanged, location changes.
- Ownership Transfer: owner changes inside one Company, location unchanged, documented with a reason.
- One production entry = one operating unit and one procurement season; Raw rice only in a RAW unit,
  Boiled rice only in a BOILED unit.
- Bag counts live in the append-only Bag Ledger Entry, apart from quintals, and cannot go negative.
Nothing here posts stock, creates Items or warehouses, or sets any rate.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

PHYSICAL = "Physical Transfer (owner unchanged)"
OWNERSHIP = "Ownership Transfer (location unchanged)"
TRANSFER_KINDS = (PHYSICAL, OWNERSHIP)
PRODUCTION_PURPOSES = ("Manufacture", "Repack", "Material Consumption for Manufacture")
RAW = "RAW"
BOILED = "BOILED"
GOVERNMENT = "Government"

LEGAL_COMPANIES = {
	"SSPP": "Shree Shyamji Paddy Processing Pvt Ltd",
	"RGFP": "Radhe Govind Food Products",
	"LGI": "Laddu Gopal Industries",
}
# Approved by the business. Applying accounting_company is a separate, reviewed step.
APPROVED_UNITS = {
	"M050414": {"abbr": "SSPP", "type": RAW},
	"M051007": {"abbr": "SSPP", "type": BOILED},
	"M050415": {"abbr": "RGFP", "type": RAW},
	"M050410": {"abbr": "RGFP", "type": BOILED},
	"M050421": {"abbr": "LGI", "type": BOILED},
}
APPROVED_LOCATIONS = {
	"SSPP": ("GODOWN", "GALI", "OPEN GODOWN"),
	"RGFP": ("MAIN GODOWN", "GALI", "CHALAN"),
	"LGI": ("PLANT", "NEW PLANT", "ECO STAND PLANT"),
}


def approved_location_names() -> list[str]:
	"""The nine Physical Location names. The owner is part of the name so SSPP GALI and RGFP GALI stay apart."""
	return [f"{abbr} {name}" for abbr, names in APPROVED_LOCATIONS.items() for name in names]


def approved_company_for_unit(unit_code: str) -> str | None:
	unit = APPROVED_UNITS.get(unit_code)
	return LEGAL_COMPANIES[unit["abbr"]] if unit else None


# ---- lookups ----


def warehouse_ownership(warehouse: str):
	"""Owner and place of a warehouse; None when it is mapped to neither an operating unit nor a physical location.

	A shared warehouse has a physical location and no operating unit (operating_unit is empty, unit_type is None):
	its stock belongs to the operating unit of each batch. A per-unit warehouse has the unit itself."""
	if not warehouse:
		return None
	row = frappe.db.get_value(
		"Warehouse", warehouse, ["name", "company", "operating_unit", "physical_location"], as_dict=True
	)
	if not row:
		return None
	unit = (row.operating_unit or "").strip()
	if not unit and not (row.physical_location or "").strip():
		return None
	row.operating_unit = unit or None
	row.unit_type = frappe.db.get_value("Mill Master", unit, "type") if unit else None
	return row


def batch_unit_column() -> bool:
	"""The Batch Operating Unit field arrives with a migration; until then nothing can be attributed by batch."""
	return bool(frappe.db.has_column("Batch", "operating_unit"))


def _batch_unit(batch_no: str) -> str:
	if not batch_no or not batch_unit_column():
		return ""
	return (frappe.db.get_value("Batch", batch_no, "operating_unit") or "").strip()


def _unit_type(unit: str) -> str:
	return (frappe.db.get_value("Mill Master", unit, "type") or "").strip() if unit else ""


def _row_unit(row, info, doc) -> str:
	"""The operating unit that owns the stock of a row: the unit of a per-unit warehouse, else the unit of its
	batch, else the Operating Unit of the Stock Entry."""
	if info and info.operating_unit:
		return info.operating_unit
	for batch in _row_batches(row):
		unit = _batch_unit(batch)
		if unit:
			return unit
	return (doc.get("operating_unit") or "").strip()


def _batch_season(batch_no: str) -> str:
	return (frappe.db.get_value("Batch", batch_no, "season") or "").strip() if batch_no else ""


def _has_batch(item_code: str) -> bool:
	return bool(cint(frappe.db.get_value("Item", item_code, "has_batch_no")))


def _row_batches(row) -> list[str]:
	"""Batches of a Stock Entry row: the batch_no field, or the batches of its bundle."""
	batch = (row.get("batch_no") or "").strip()
	if batch:
		return [batch]
	bundle = (row.get("serial_and_batch_bundle") or "").strip()
	if bundle:
		return [
			b
			for b in frappe.get_all(
				"Serial and Batch Entry", filters={"parent": bundle}, pluck="batch_no", distinct=True
			)
			if b
		]
	return []


def _row_infos(doc):
	return [
		(row, warehouse_ownership(row.get("s_warehouse")), warehouse_ownership(row.get("t_warehouse")))
		for row in (doc.get("items") or [])
	]


# ---- Stock Entry rules ----


def validate_stock_entry_foundation(doc, method=None):
	infos = _row_infos(doc)
	if not any(src or tgt for _row, src, tgt in infos):
		return  # not an operating-unit warehouse: leave the entry alone

	if cint(doc.get("add_to_transit")):
		frappe.throw(_("Transfers through a transit warehouse are not set up yet. Use a direct transfer."))

	settings = frappe.get_cached_doc("Stock Posting Settings")
	_validate_unit_matches_receipt(doc, infos)
	_validate_rice_in_matching_unit(settings, infos, doc)
	_validate_shared_batches_have_unit(infos)
	if doc.purpose == "Material Transfer":
		_validate_transfer(doc, infos)
	elif doc.purpose in PRODUCTION_PURPOSES:
		_validate_production(doc, infos)
	else:
		_validate_owner_kept(infos)
		_validate_batches_have_season(infos)


def _validate_unit_matches_receipt(doc, infos):
	"""A receipt linked to a GRN Note lands in a warehouse of its own operating unit, or in the shared warehouse of
	the legal Company that operating unit accounts to."""
	unit = (doc.get("operating_unit") or "").strip()
	if not (doc.get("grn_note") and unit):
		return
	company = None
	for row, _src, tgt in infos:
		if not tgt:
			frappe.throw(_("Row {0}: the warehouse must be mapped to a physical location or to operating unit {1}.").format(row.idx, unit))
		if tgt.operating_unit:
			if tgt.operating_unit != unit:
				frappe.throw(_("Row {0}: the warehouse must belong to operating unit {1}.").format(row.idx, unit))
			continue
		company = company or frappe.db.get_value("Mill Master", unit, "accounting_company")
		if tgt.company != company:
			frappe.throw(
				_("Row {0}: warehouse {1} belongs to {2}, but operating unit {3} accounts to {4}.").format(
					row.idx, tgt.name, tgt.company, unit, company
				)
			)


def _validate_rice_in_matching_unit(settings, infos, doc=None):
	"""Raw rice belongs to a RAW operating unit and Boiled rice to a BOILED one. In a shared warehouse the unit is the
	Operating Unit of the Stock Entry."""
	wanted = {}
	if settings.raw_rice_item:
		wanted[settings.raw_rice_item] = RAW
	if settings.boiled_rice_item:
		wanted[settings.boiled_rice_item] = BOILED
	for row, _src, tgt in infos:
		need = wanted.get(row.get("item_code"))
		if not (need and tgt):
			continue
		unit_type = tgt.unit_type
		if not tgt.operating_unit:
			unit = ((doc.get("operating_unit") if doc else "") or "").strip()
			if not unit:
				frappe.throw(
					_("Row {0}: enter the Operating Unit on the Stock Entry. Rice kept in a shared warehouse belongs to it.").format(row.idx)
				)
			unit_type = _unit_type(unit)
		if unit_type != need:
			frappe.throw(
				_("Row {0}: {1} rice can only be kept by a {1} operating unit.").format(row.idx, need.title())
			)


def _validate_batches_have_season(infos):
	for row, src, tgt in infos:
		if not (src or tgt):
			continue
		for batch in _row_batches(row):
			if not _batch_season(batch):
				frappe.throw(_("Row {0}: Batch {1} has no Procurement Season.").format(row.idx, batch))


def _validate_shared_batches_have_unit(infos):
	"""Stock in a shared warehouse is attributed to the operating unit of its batch, so every batch that goes in or out
	of one must carry an Operating Unit."""
	for row, src, tgt in infos:
		if not any(info and not info.operating_unit for info in (src, tgt)):
			continue
		if not batch_unit_column():
			frappe.throw(_("Row {0}: the Batch Operating Unit field is not set up yet, so stock cannot be kept in a shared warehouse.").format(row.idx))
		for batch in _row_batches(row):
			if not _batch_unit(batch):
				frappe.throw(
					_("Row {0}: Batch {1} has no Operating Unit. Stock in a shared warehouse belongs to the unit of its batch.").format(row.idx, batch)
				)


def _validate_owner_kept(infos):
	"""Any other entry that moves stock between two warehouses (e.g. Material Transfer for Manufacture,
	Send to Subcontractor) cannot change the owner. Only a documented Ownership Transfer does that."""
	for row, src, tgt in infos:
		if not (row.get("s_warehouse") and row.get("t_warehouse")):
			continue
		if not (src and tgt) or src.operating_unit != tgt.operating_unit or src.company != tgt.company:
			frappe.throw(
				_("Row {0}: this entry cannot change the owner of the stock. Use a Material Transfer with Transfer Kind Ownership Transfer.").format(
					row.idx
				)
			)


def _validate_transfer(doc, infos):
	kind = (doc.get("transfer_kind") or "").strip()
	if kind not in TRANSFER_KINDS:
		frappe.throw(_("Select the Transfer Kind: Physical Transfer or Ownership Transfer."))
	for row, src, tgt in infos:
		if not (src and tgt):
			frappe.throw(
				_("Row {0}: both warehouses must be mapped to a physical location.").format(
					row.idx
				)
			)
		same_unit = src.operating_unit == tgt.operating_unit
		same_place = src.physical_location == tgt.physical_location
		shared = not (src.operating_unit and tgt.operating_unit)
		if kind == PHYSICAL:
			owner_changes = src.company != tgt.company
			if shared:
				# the owner is the operating unit of the batch, so it can only change if a per-unit warehouse says otherwise
				from_unit, to_unit = _row_unit(row, src, doc), _row_unit(row, tgt, doc)
				owner_changes = owner_changes or bool(from_unit and to_unit and from_unit != to_unit)
			else:
				owner_changes = owner_changes or not same_unit
			if owner_changes:
				frappe.throw(
					_("Row {0}: a Physical Transfer keeps the owner. Use an Ownership Transfer to change it.").format(
						row.idx
					)
				)
			if same_place:
				frappe.throw(_("Row {0}: a Physical Transfer must change the physical location.").format(row.idx))
		else:
			if shared:
				frappe.throw(
					_("Row {0}: stock in a shared warehouse belongs to the operating unit of its batch. Moving it to another operating unit is not set up yet.").format(row.idx)
				)
			if same_unit:
				frappe.throw(_("Row {0}: an Ownership Transfer must change the operating unit.").format(row.idx))
			if src.company != tgt.company:
				frappe.throw(
					_("Row {0}: ownership transfer between legal Companies needs inter-company documents, which are not built yet.").format(
						row.idx
					)
				)
			if not same_place:
				frappe.throw(
					_("Row {0}: an Ownership Transfer keeps the physical location. Move the stock in a separate Physical Transfer.").format(
						row.idx
					)
				)
	if kind == OWNERSHIP and not (doc.get("ownership_transfer_reason") or "").strip():
		frappe.throw(_("Enter the reason for the Ownership Transfer."))
	_validate_batches_have_season(infos)


def _validate_production(doc, infos):
	"""One operating unit and one procurement season per production entry."""
	units = set()
	for row, src, tgt in infos:
		if (row.get("s_warehouse") and not src) or (row.get("t_warehouse") and not tgt):
			frappe.throw(_("Row {0}: every warehouse in a production entry must be mapped to a physical location or an operating unit.").format(row.idx))
		for info in (src, tgt):
			if not info:
				continue
			unit = _row_unit(row, info, doc)
			if not unit:
				frappe.throw(_("Row {0}: enter the Operating Unit on the Stock Entry; the warehouse is shared.").format(row.idx))
			units.add(unit)
	if len(units) > 1:
		frappe.throw(_("A production entry uses one operating unit. Found: {0}.").format(", ".join(sorted(units))))

	consumed, produced = set(), set()
	for row, src, tgt in infos:
		item = row.get("item_code")
		is_batch_item = _has_batch(item)
		batches = _row_batches(row)
		if is_batch_item and not batches:
			frappe.throw(
				_("Row {0}: enter the batch for {1}. Seasons are never picked automatically in production.").format(
					row.idx, item
				)
			)
		seasons = set()
		for batch in batches:
			season = _batch_season(batch)
			if not season:
				frappe.throw(_("Row {0}: Batch {1} has no Procurement Season.").format(row.idx, batch))
			seasons.add(season)
		(consumed if src else produced).update(seasons)
	if len(consumed) > 1:
		frappe.throw(_("A production batch cannot mix procurement seasons. Found: {0}.").format(", ".join(sorted(consumed))))
	if consumed and produced and produced != consumed:
		frappe.throw(
			_("Produced stock must carry the season of the paddy used ({0}).").format(", ".join(sorted(consumed)))
		)


# ---- Bag ledger ----
# The Bag Ledger tracks PHYSICAL bags of GOVERNMENT paddy only. A row counts when its Item is the government paddy Item
# and every batch on it was posted as Government procurement (Batch.procurement_type, set when a GRN Note with a valid
# Pass Unique Key is posted). Local paddy, rice, by-products and anything unidentified are never counted, and are
# never guessed from the supplier, warehouse, Item or bag count.


def _government_paddy_item() -> str:
	return (frappe.get_cached_doc("Stock Posting Settings").get("government_paddy_item") or "").strip()


def _batch_procurement_type(batch_no: str) -> str:
	return (frappe.db.get_value("Batch", batch_no, "procurement_type") or "").strip() if batch_no else ""


def is_government_paddy_row(row, batches=None) -> bool:
	paddy = _government_paddy_item()
	if not paddy or row.get("item_code") != paddy:
		return False
	batches = _row_batches(row) if batches is None else batches
	return bool(batches) and all(_batch_procurement_type(b) == GOVERNMENT for b in batches)



def bag_entries(doc) -> list[dict]:
	"""Bag movements of a Stock Entry, one per (row, side) that touches an operating-unit warehouse."""
	entries = []
	for row in doc.get("items") or []:
		bags = cint(row.get("no_of_bags"))
		if bags <= 0:
			continue
		batches = _row_batches(row)
		if (
			row.get("item_code") == _government_paddy_item()
			and len(batches) > 1
			and GOVERNMENT in {_batch_procurement_type(b) for b in batches}
			and not is_government_paddy_row(row, batches)
		):
			frappe.throw(_("Row {0}: government and non-government batches are mixed in one row. Split the row so the bags can be attributed.").format(row.idx))
		if not is_government_paddy_row(row, batches):
			continue  # local paddy, rice, by-products and unidentified rows are not in the government bag ledger
		if len(batches) > 1:
			frappe.throw(_("Row {0}: enter bags per batch. Use one batch per row.").format(row.idx))
		batch = batches[0] if batches else ""
		for side, warehouse, sign in (
			("OUT", row.get("s_warehouse"), -1),
			("IN", row.get("t_warehouse"), 1),
		):
			info = warehouse_ownership(warehouse)
			if not info:
				continue
			entries.append(
				{
					"entry_key": f"{doc.name}|{row.name}|{side}",
					"posting_date": doc.get("posting_date"),
					"bags": sign * bags,
					"company": info.company,
					"operating_unit": _row_unit(row, info, doc),
					"physical_location": info.physical_location,
					"warehouse": warehouse,
					"item_code": row.get("item_code"),
					"batch_no": batch,
					"season": _batch_season(batch),
					"voucher_type": doc.doctype,
					"voucher_no": doc.name,
					"voucher_detail_no": row.name,
				}
			)
	return entries


def bag_balance(warehouse: str, item_code: str, batch_no: str, lock: bool = False) -> int:
	sql = (
		"select ifnull(sum(bags), 0) from `tabBag Ledger Entry` "
		"where warehouse = %s and item_code = %s and ifnull(batch_no, '') = %s"
	)
	return cint(frappe.db.sql(sql + (" for update" if lock else ""), (warehouse, item_code, batch_no or ""))[0][0])


def check_bag_balance_before_submit(doc, method=None):
	"""Bags leaving a warehouse cannot exceed the bags held there, and stock leaving a warehouse that holds bags
	of that batch must say how many bags go (otherwise the bag balance drifts away from the quantity)."""
	for row in doc.get("items") or []:
		if cint(row.get("no_of_bags")) > 0 or not row.get("s_warehouse"):
			continue
		if not warehouse_ownership(row.get("s_warehouse")) or not is_government_paddy_row(row):
			continue
		for batch in _row_batches(row) or [""]:
			held = bag_balance(row.get("s_warehouse"), row.get("item_code"), batch)
			if held > 0:
				frappe.throw(
					_("Row {0}: {1} holds {2} bags of {3}. Enter the number of bags that leave with this stock.").format(
						row.idx, row.get("s_warehouse"), held, row.get("item_code")
					),
					title=_("Bags Required"),
				)
	needed = {}
	for entry in bag_entries(doc):
		if entry["bags"] < 0:
			key = (entry["warehouse"], entry["item_code"], entry["batch_no"])
			needed[key] = needed.get(key, 0) - entry["bags"]
	for (warehouse, item_code, batch_no), out in needed.items():
		held = bag_balance(warehouse, item_code, batch_no, lock=True)
		if held - out < 0:
			frappe.throw(
				_("Not enough bags of {0} in {1}: {2} held, {3} needed.").format(item_code, warehouse, held, out),
				title=_("Negative Bag Balance"),
			)


def record_bag_ledger(doc, method=None):
	"""On submit: one ledger row per bag movement. A repeated call adds nothing."""
	for entry in bag_entries(doc):
		if frappe.db.exists("Bag Ledger Entry", {"entry_key": entry["entry_key"]}):
			continue
		frappe.get_doc({"doctype": "Bag Ledger Entry", **entry}).insert(ignore_permissions=True)


def reverse_bag_ledger(doc, method=None):
	"""On cancel: one opposite row per original row. The originals stay (append-only)."""
	originals = frappe.get_all(
		"Bag Ledger Entry",
		filters={"voucher_no": doc.name, "is_reversal": 0},
		fields=["*"],
	)
	pending = [r for r in originals if not frappe.db.exists("Bag Ledger Entry", {"entry_key": f"{r.entry_key}|REV"})]
	# Taking back bags that were received must not leave a warehouse with fewer bags than zero.
	taken_back = {}
	for row in pending:
		if cint(row.bags) > 0:
			key = (row.warehouse, row.item_code, row.batch_no or "")
			taken_back[key] = taken_back.get(key, 0) + cint(row.bags)
	for (warehouse, item_code, batch_no), bags in taken_back.items():
		held = bag_balance(warehouse, item_code, batch_no, lock=True)
		if held - bags < 0:
			frappe.throw(
				_("Cannot cancel: {0} bags of {1} were received in {2}, but only {3} are still there. The rest were moved or used.").format(
					bags, item_code, warehouse, held
				),
				title=_("Negative Bag Balance"),
			)
	for row in pending:
		key = f"{row.entry_key}|REV"
		frappe.get_doc(
			{
				"doctype": "Bag Ledger Entry",
				**{
					field: row[field]
					for field in (
						"posting_date", "company", "operating_unit", "physical_location", "warehouse",
						"item_code", "batch_no", "season", "voucher_type", "voucher_no", "voucher_detail_no",
					)
				},
				"entry_key": key,
				"bags": -cint(row.bags),
				"is_reversal": 1,
				"reverses": row.name,
			}
		).insert(ignore_permissions=True)


# ---- Mill Master ----


def validate_mill_master_mapping(doc, method=None):
	"""Accounting Company must be the approved legal Company, and is locked once stock exists."""
	company = (doc.get("accounting_company") or "").strip()
	approved = approved_company_for_unit(doc.name)
	if company and approved and company != approved:
		frappe.throw(
			_("Operating unit {0} belongs to {1}. Accounting Company cannot be {2}.").format(doc.name, approved, company)
		)
	before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	old = (before.get("accounting_company") if before else "") or ""
	if old and old != company and _unit_has_stock(doc.name):
		frappe.throw(
			_("Operating unit {0} already has stock. Its Accounting Company can no longer be changed.").format(doc.name)
		)


def _unit_has_stock(unit: str) -> bool:
	"""Stock of the unit: in its own warehouses (older setup), or posted for it in a shared warehouse."""
	warehouses = frappe.get_all("Warehouse", filters={"operating_unit": unit}, pluck="name")
	if warehouses and frappe.db.exists("Stock Ledger Entry", {"warehouse": ["in", warehouses], "is_cancelled": 0}):
		return True
	return bool(frappe.db.exists("Stock Entry", {"operating_unit": unit, "docstatus": 1}))


# ---- Read-only mapping status ----


@frappe.whitelist()
def get_foundation_status() -> dict:
	"""What is mapped and what is missing. Reads only; changes nothing."""
	frappe.has_permission("Mill Master", "read", throw=True)
	issues, units, locations = [], [], []
	for code, spec in APPROVED_UNITS.items():
		mill = frappe.db.get_value(
			"Mill Master", code, ["name", "type", "company", "accounting_company"], as_dict=True
		)
		expected = LEGAL_COMPANIES[spec["abbr"]]
		company_exists = bool(frappe.db.exists("Company", expected))
		row = {
			"unit": code, "exists": bool(mill), "type_ok": bool(mill and mill.type == spec["type"]),
			"expected_company": expected, "expected_company_exists": company_exists,
			"accounting_company": (mill.accounting_company if mill else None) or "",
		}
		row["mapped"] = row["accounting_company"] == expected
		units.append(row)
		if not mill:
			issues.append(f"Mill Master {code} is missing.")
		elif not row["type_ok"]:
			issues.append(f"Mill Master {code} type is {mill.type}, approved type is {spec['type']}.")
		if not company_exists:
			issues.append(f"Legal Company '{expected}' does not exist yet.")
		if mill and not row["mapped"]:
			issues.append(f"{code}: Accounting Company not set to '{expected}'.")
	for abbr, names in APPROVED_LOCATIONS.items():
		for name in names:
			full = f"{abbr} {name}"
			company = frappe.db.get_value("Physical Location", full, "company")
			locations.append({"location": full, "exists": company is not None, "company": company or ""})
			if company is None:
				issues.append(f"Physical Location '{full}' does not exist yet.")
			elif company != LEGAL_COMPANIES[abbr]:
				issues.append(f"Physical Location '{full}' belongs to '{company}'.")
	return {"units": units, "locations": locations, "issues": issues}
