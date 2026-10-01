# Copyright (c) 2026, Profezzo and contributors
"""TP and Chhatni fulfillment status for government GRN (per Pass Unique Key)."""

from __future__ import annotations

import frappe
from frappe.utils import flt

# Allow up to 0.3 percentage points below chhatni rate (e.g. 1% required → 0.7% still accepted).
CHHATNI_PCT_POINT_TOLERANCE = 0.3

CHHATNI_NOT_RECEIVED = "Chhatni Not Received"
CHHATNI_PENDING = "Chhatni Pending"
CHHATNI_RECEIVED = "Chhatni Received"

REMARK_TP_NOT_FILLED = (
	"Chhatni cannot be calculated because the transit pass (TP) quantity is not fully received yet."
)


def chhatni_fulfillment_status(tp_qty: float, cumulative_received: float, chhatni_kg_per_quintal: float) -> str:
	"""
	Chhatni Received when overfill (as % of TP) is within 0.3 points of chhatni rate.
	Example: chhatni 1% → accept from 0.7% overfill upward; chhatni 9% → need ~8.7%+.
	"""
	tp_qty = flt(tp_qty)
	cumulative_received = flt(cumulative_received)
	chhatni_kg_per_quintal = flt(chhatni_kg_per_quintal)
	if tp_qty <= 0 or cumulative_received < tp_qty:
		return ""
	if chhatni_kg_per_quintal <= 0:
		return CHHATNI_PENDING
	overfill = flt(cumulative_received - tp_qty, 3)
	overfill_pct = flt(overfill / tp_qty * 100, 4)
	min_acceptable_pct = flt(max(chhatni_kg_per_quintal - CHHATNI_PCT_POINT_TOLERANCE, 0), 4)
	if overfill_pct >= min_acceptable_pct:
		return CHHATNI_RECEIVED
	return CHHATNI_PENDING


def grn_received_quantity(grn) -> float:
	entry_qty = sum(flt(row.entry_quantity) for row in (grn.entry_details or []))
	return flt(grn.net_weight) + entry_qty


def _sort_key(grn) -> tuple:
	return (
		grn.receipt_date or "",
		str(grn.receipt_time or ""),
		grn.creation or "",
		grn.name or "",
	)


def refresh_tp_fulfillment_for_pass(pass_unique_key: str | None, trigger_grn: str | None = None):
	"""Recompute TP/Chhatni status for all government GRNs on this pass."""
	key = (pass_unique_key or "").strip()
	if not key:
		return

	if getattr(frappe.local, "_refreshing_tp_pass", None) == key:
		return
	frappe.local._refreshing_tp_pass = key
	try:
		_refresh_tp_fulfillment_for_pass(key)
	finally:
		frappe.local._refreshing_tp_pass = None


def _refresh_tp_fulfillment_for_pass(pass_unique_key: str):
	rows = frappe.get_all(
		"GRN Note",
		filters={
			"pass_unique_key": pass_unique_key,
			"is_local_procurement": 0,
			"docstatus": ["<", 2],
		},
		fields=[
			"name",
			"receipt_date",
			"receipt_time",
			"creation",
			"net_weight",
			"tp_quantity",
			"chhatni",
		],
		order_by="receipt_date asc, receipt_time asc, creation asc",
	)
	if not rows:
		return

	tp_qty = max(flt(r.tp_quantity) for r in rows)
	if not tp_qty:
		tp_qty = flt(
			frappe.db.get_value(
				"PPAS Transit Pass",
				{"pass_unique_key": pass_unique_key},
				"quantity",
			)
		)

	grn_docs: list[frappe.model.document.Document] = []
	for row in rows:
		grn_docs.append(frappe.get_doc("GRN Note", row.name))

	grn_docs.sort(key=_sort_key)

	cumulative = 0.0
	tp_completed_grn: str | None = None
	updates: dict[str, dict] = {}

	for doc in grn_docs:
		received = grn_received_quantity(doc)
		prev_cumulative = cumulative
		cumulative = flt(cumulative + received, 3)

		tp_status = "In Progress"
		chhatni_status = ""
		chhatni_remark = ""

		if tp_qty > 0 and cumulative >= tp_qty and not tp_completed_grn:
			tp_completed_grn = doc.name
			tp_status = "TP Completed"
			chhatni_status = chhatni_fulfillment_status(tp_qty, cumulative, doc.chhatni)
		elif tp_qty > 0 and cumulative < tp_qty:
			chhatni_status = CHHATNI_NOT_RECEIVED
			chhatni_remark = REMARK_TP_NOT_FILLED

		updates[doc.name] = {
			"received_quantity": received,
			"tp_cumulative_received": cumulative,
			"tp_fulfillment_status": tp_status,
			"chhatni_fulfillment_status": chhatni_status,
			"chhatni_fulfillment_remark": chhatni_remark,
		}

	for name, values in updates.items():
		frappe.db.set_value("GRN Note", name, values, update_modified=False)


def clear_tp_fulfillment_fields(grn):
	grn.received_quantity = 0
	grn.tp_cumulative_received = 0
	grn.tp_fulfillment_status = ""
	grn.chhatni_fulfillment_status = ""
	grn.chhatni_fulfillment_remark = ""
