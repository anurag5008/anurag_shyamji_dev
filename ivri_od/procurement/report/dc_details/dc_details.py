# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""DC Details: rice due, DCs issued and lots delivered, one line per mill for a season.

- Paddy Received: sum of Target Quantity in Target Allocation (all PPCs of the mill) for the season.
- Driage: Raw mills only, Paddy Received x Driage % (Rice Delivery Setup "Raw").
- CMR Due: Paddy After Driage x CMR % of the mill's type (Mill Master Type -> Rice Delivery Setup).
- Total Lot: CMR Due / Lot Quantity (Rice Lot Quantity, same for all mills), rounded.
- FCI / RRC DC Issue and Delivery: lots on the DCs and lots delivered, as counted in DC Track
  (View DC from DCRO; DCRO DC Transit Challan for FCI, SCMS Lot Search for RRC).
  A DC is in the season when its KMS Year starts with the season year (2025-26 for
  Kharif 2025) and its season, when read, is the crop season.
- FCI Pending: lots of the DC in DCRO DC Transit Challan whose "Pending At" is not
  "Approved" (e.g. "Assitant Depot"). Still counted in FCI Delivery.
- RRC Pending: lots of the DC in SCMS Transit Challan RRC that are not in SCMS Lot Search yet
  (sent to the RRC, not received).
  Both are shown only: no balance, total or Delivery % uses them.
- VR Pending: not read yet, always 0.
- Delivery %: rice delivered (Total Delivery x Lot Quantity) against CMR Due."""

import math

import frappe
from frappe import _
from frappe.utils import flt

from ivri_od.procurement.report.dc_track.dc_track import (
	DC_NO,
	LOT_NO,
	MILL,
	NOT_DELIVERED,
	_add_deliveries,
	_cell,
	_dc,
	_dc_no,
	_dc_type,
	_dcs_from_view_dc,
	_load,
	_records,
)

# (site, section) of the rows read for the pending lots.
FCI_CHALLAN = ("DCRO", "DC Transit Challan")
RRC_CHALLAN = ("SCMS", "Transit Challan RRC")
RRC_RECEIVED = ("SCMS", "Lot Search")
# Status of a challan row (letters and digits only, lower case); a rejected or cancelled challan is not pending.
CHALLAN_STATUS = ["lotchallanreceiptstatus", "challanstatus", "status"]

LOT_COLUMNS = (
	"total_lot",
	"fci_dc_issue",
	"fci_delivery",
	"fci_balance",
	"fci_pending",
	"rrc_dc_issue",
	"rrc_delivery",
	"rrc_balance",
	"rrc_pending",
	"total_delivery",
	"total_dc_issued",
	"total_dc_issue_balance",
	"total_delivery_balance",
	"vr_pending",
)
QTY_COLUMNS = ("paddy_received", "driage", "paddy_after_driage", "cmr_due")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.season:
		return _columns(), [], _("Select a Season.")
	season = frappe.db.get_value("Season Master", filters.season, ["crop_season", "year"], as_dict=True)
	if not season:
		frappe.throw(_("Season {0} not found").format(filters.season))

	setup = {
		row.rice_type.upper(): row
		for row in frappe.get_all("Rice Delivery Setup", fields=["rice_type", "cmr_percentage", "driage_percentage"])
	}
	paddy = _paddy_received(filters.season)
	lots = _dc_lots(season)

	data, missing = [], set()
	for mill in _mills(filters, paddy, lots):
		rate = setup.get((mill.type or "").upper())
		if not rate:
			missing.add(mill.type or _("(no Type)"))
		data.append(_line(mill, rate, paddy.get(mill.name, 0), lots.get(mill.name.upper(), {})))
	if data:
		data.append(_total(data))

	message = None
	if missing:
		message = _("Rice Delivery Setup missing for: {0}. CMR Due is 0 for these mills.").format(
			", ".join(sorted(missing))
		)
	return _columns(), data, message


def _paddy_received(season) -> dict:
	"""{mill: paddy (Qtl)}: Target Quantity of every PPC allotted to the mill."""
	rows = frappe.get_all(
		"Target Allocation",
		filters={"season": season},
		fields=["mill_name", {"SUM": "target_quantity", "as": "qty"}],
		group_by="mill_name",
	)
	return {r.mill_name: flt(r.qty) for r in rows if r.mill_name}


def _dc_lots(season) -> dict:
	"""{MILL CODE: {fci_issue, fci_delivery, fci_pending, rrc_issue, rrc_delivery, rrc_pending}}
	from the season's DCs."""
	dcs = _dcs_from_view_dc()
	_add_deliveries(dcs)
	_add_pending(dcs)
	lots = {}
	for dc in dcs.values():
		if not dc["mill_id"] or not _in_season(dc, season):
			continue
		kind = dc["dc_type"].lower()
		if kind not in ("fci", "rrc"):
			continue
		mill = lots.setdefault(dc["mill_id"].upper(), {})
		mill[f"{kind}_issue"] = mill.get(f"{kind}_issue", 0) + (dc["total_lots"] or 0)
		mill[f"{kind}_delivery"] = mill.get(f"{kind}_delivery", 0) + len(dc["lots"])
		mill[f"{kind}_pending"] = mill.get(f"{kind}_pending", 0) + len(dc.get("pending") or ())
	return lots


def _add_pending(dcs: dict):
	"""Put each DC's pending lots in dc["pending"] (a set of Lot No.).
	FCI: DCRO Transit Challan rows whose Pending At is not Approved.
	RRC: SCMS Transit Challan RRC lots not in SCMS Lot Search (any status: it reached the RRC)."""
	received = set()
	for record in _records(*RRC_RECEIVED):
		cells = _load(record.row_data)
		received.add((_dc_no(_cell(cells, DC_NO)), _lot_no(_cell(cells, LOT_NO))))

	for source in (FCI_CHALLAN, RRC_CHALLAN):
		for record in _records(*source):
			cells = _load(record.row_data)
			dc_no, lot = _dc_no(_cell(cells, DC_NO)), _lot_no(_cell(cells, LOT_NO))
			if not dc_no or not lot:
				continue
			if source == FCI_CHALLAN:
				pending_at = _cell(cells, ["pendingat"])
				if not pending_at or pending_at.casefold() == "approved" or NOT_DELIVERED.search(pending_at):
					continue
			elif (dc_no, lot) in received or NOT_DELIVERED.search(_cell(cells, CHALLAN_STATUS)):
				continue
			dc = dcs.get(dc_no)
			if dc is None:
				dc = dcs[dc_no] = _dc(
					dc_no,
					mill_id=_cell(cells, MILL) or record.mill_id or "",
					kms_year=_cell(cells, ["kmsyear", "kms"]),
					dc_type=_dc_type(dc_no, cells, []),
				)
			dc.setdefault("pending", set()).add(lot)


def _lot_no(value) -> str:
	"""Lot No. as compared between reports: "07" and "7" are the same lot."""
	value = (value or "").strip()
	return (value.lstrip("0") or value) if value.isdigit() else value.upper()


def _in_season(dc, season) -> bool:
	"""KMS Year 2025-26 is season year 2025; the DC's season (if read) must be the crop season."""
	if not (dc["kms_year"] or "").startswith(season.year or "-"):
		return False
	return not dc["season"] or dc["season"].casefold() == (season.crop_season or "").casefold()


def _mills(filters, paddy, lots):
	"""Every active mill, and any other mill with paddy or DCs in the season."""
	mills = frappe.get_all(
		"Mill Master",
		fields=["name", "company", "type", "is_active"],
		order_by="company asc, name asc",
	)
	lot_qty = flt(frappe.db.get_single_value("Rice Lot Quantity", "lot_quantity"))
	for mill in mills:
		mill.lot_quantity = lot_qty
	return [
		m
		for m in mills
		if (not filters.mill or m.name == filters.mill)
		and (m.is_active or m.name in paddy or m.name.upper() in lots)
	]


def _line(mill, rate, paddy_received, lots) -> dict:
	driage_pct = flt(rate.driage_percentage) if rate and rate.rice_type == "Raw" else 0
	driage = flt(paddy_received * driage_pct / 100, 2)
	after_driage = flt(paddy_received - driage, 2)
	cmr_due = flt(after_driage * flt(rate.cmr_percentage) / 100, 2) if rate else 0
	lot_qty = flt(mill.lot_quantity)
	total_lot = _round_half_up(cmr_due / lot_qty) if lot_qty else 0

	fci_issue, fci_delivery = lots.get("fci_issue", 0), lots.get("fci_delivery", 0)
	rrc_issue, rrc_delivery = lots.get("rrc_issue", 0), lots.get("rrc_delivery", 0)
	# Shown only: the pending lots are not part of any balance or total below.
	fci_pending, rrc_pending = lots.get("fci_pending", 0), lots.get("rrc_pending", 0)
	total_delivery = fci_delivery + rrc_delivery
	total_issued = fci_issue + rrc_issue
	return {
		"mill": mill.name,
		"mill_name": mill.company,
		"mill_type": mill.type,
		"paddy_received": flt(paddy_received, 2),
		"driage": driage,
		"paddy_after_driage": after_driage,
		"cmr_due": cmr_due,
		"total_lot": total_lot,
		"fci_dc_issue": fci_issue,
		"fci_delivery": fci_delivery,
		"fci_balance": fci_issue - fci_delivery,
		"fci_pending": fci_pending,
		"rrc_dc_issue": rrc_issue,
		"rrc_delivery": rrc_delivery,
		"rrc_balance": rrc_issue - rrc_delivery,
		"rrc_pending": rrc_pending,
		"total_delivery": total_delivery,
		"total_dc_issued": total_issued,
		"total_dc_issue_balance": total_lot - total_issued,
		"total_delivery_balance": total_lot - total_delivery,
		"vr_pending": 0,
		# Kept for the total row: rice (Qtl) in the delivered lots.
		"delivered_rice": total_delivery * lot_qty,
		"delivery_percent": _percent(total_delivery * lot_qty, cmr_due),
	}


def _total(data) -> dict:
	total = {"mill_name": _("Total"), "is_total_row": 1}
	for field in QTY_COLUMNS:
		total[field] = flt(sum(r[field] for r in data), 2)
	for field in LOT_COLUMNS:
		total[field] = sum(r[field] for r in data)
	total["delivery_percent"] = _percent(sum(r["delivered_rice"] for r in data), total["cmr_due"])
	return total


def _percent(part, whole):
	return flt(part * 100 / whole, 2) if whole else 0


def _round_half_up(value) -> int:
	return int(math.floor(value + 0.5))


def _columns():
	def lot(fieldname, label, width=90):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": "Int", "width": width}

	def qty(fieldname, label, width=130):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": "Float", "precision": 2, "width": width}

	return [
		{"fieldname": "mill_name", "label": _("Mill"), "fieldtype": "Data", "width": 260},
		# Hidden (the Mill name already says Boiled / Raw); kept in the rows for the charts and filters.
		{"fieldname": "mill", "label": _("Mill No."), "fieldtype": "Link", "options": "Mill Master", "width": 100, "hidden": 1},
		{"fieldname": "mill_type", "label": _("Type"), "fieldtype": "Data", "width": 80, "hidden": 1},
		qty("paddy_received", "Paddy Received"),
		qty("driage", "Driage", 100),
		qty("paddy_after_driage", "Paddy After Driage"),
		qty("cmr_due", "CMR Due"),
		lot("total_lot", "Total Lot"),
		lot("fci_dc_issue", "FCI DC Issue"),
		lot("fci_delivery", "FCI Delivery"),
		lot("fci_balance", "FCI Balance"),
		lot("fci_pending", "FCI Pending"),
		lot("rrc_dc_issue", "RRC DC Issue"),
		lot("rrc_delivery", "RRC Delivery"),
		lot("rrc_balance", "RRC Balance"),
		lot("rrc_pending", "RRC Pending"),
		lot("total_delivery", "Total Delivery", 100),
		lot("total_dc_issued", "Total DC Issued", 110),
		lot("total_dc_issue_balance", "Total DC Issue Balance", 130),
		lot("total_delivery_balance", "Total Delivery Balance", 130),
		lot("vr_pending", "VR Pending"),
		{"fieldname": "delivery_percent", "label": _("Delivery %"), "fieldtype": "Percent", "width": 100},
	]
