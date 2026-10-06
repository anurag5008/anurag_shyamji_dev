# Copyright (c) 2026, Profezzo and contributors
"""TP and Chhatni fulfillment status for government GRN (per Pass Unique Key)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

CHHATNI_NOT_RECEIVED = "Chhatni Not Received"
CHHATNI_PENDING = "Chhatni Pending"
CHHATNI_RECEIVED = "Chhatni Received"
CHHATNI_OVER_FILLED = "Over Filled Chhatni Received"
# A shortfall up to this quantity (QT) still counts as Chhatni Received.
# Any amount above TP + chhatni is over filled; there is no plus threshold.
CHHATNI_BALANCE_THRESHOLD_QT = 0.3

REMARK_TP_NOT_FILLED = (
	"Chhatni cannot be calculated because the transit pass (TP) quantity is not fully received yet."
)


def required_chhatni_qt(tp_qty: float, chhatni_percentage: float) -> float:
	"""Required chhatni quantity (QT) = TP quantity × chhatni % ÷ 100."""
	return flt(flt(tp_qty) * flt(chhatni_percentage) / 100, 3)


def received_chhatni_pct(cumulative_received: float, tp_qty: float) -> float:
	"""(Pass total received − TP quantity) ÷ TP quantity × 100. Zero until TP is filled."""
	tp_qty = flt(tp_qty)
	if tp_qty <= 0:
		return 0.0
	overfill = max(flt(cumulative_received) - tp_qty, 0)
	return flt(overfill / tp_qty * 100, 4)


def tp_chhatni_balance_qt(tp_qty: float, cumulative_received: float, chhatni_percentage: float) -> float:
	"""Pass total received − (TP quantity + required chhatni).

	Positive: received above TP plus chhatni (over filled).
	Zero: TP and chhatni exactly received.
	Negative: still short of TP plus chhatni.
	"""
	tp_qty = flt(tp_qty)
	if tp_qty <= 0:
		return 0.0
	required = required_chhatni_qt(tp_qty, chhatni_percentage)
	return flt(flt(cumulative_received) - tp_qty - required, 3)


def chhatni_fulfillment_status(
	tp_qty: float,
	cumulative_received: float,
	chhatni_kg_per_quintal: float,
) -> str:
	status, _ = evaluate_chhatni_fulfillment(
		tp_qty,
		cumulative_received,
		chhatni_kg_per_quintal,
	)
	return status


def evaluate_chhatni_fulfillment(
	tp_qty: float,
	cumulative_received: float,
	chhatni_kg_per_quintal: float,
) -> tuple[str, str]:
	tp_qty = flt(tp_qty)
	cumulative_received = flt(cumulative_received)
	chhatni_kg_per_quintal = flt(chhatni_kg_per_quintal)

	if tp_qty <= 0 or cumulative_received < tp_qty:
		return CHHATNI_NOT_RECEIVED, REMARK_TP_NOT_FILLED

	overfill_qt = flt(cumulative_received - tp_qty, 3)
	required_qt = required_chhatni_qt(tp_qty, chhatni_kg_per_quintal)
	received_pct = received_chhatni_pct(cumulative_received, tp_qty)

	remark = _(
		"Pass total received {0} QT minus TP {1} QT is {2} QT ({3}%). "
		"Required chhatni is {4} QT (TP × {5}% ÷ 100)."
	).format(
		flt(cumulative_received, 3),
		flt(tp_qty, 3),
		flt(overfill_qt, 3),
		flt(received_pct, 2),
		flt(required_qt, 3),
		flt(chhatni_kg_per_quintal, 2) if chhatni_kg_per_quintal > 0 else "—",
	)

	if chhatni_kg_per_quintal <= 0:
		return CHHATNI_PENDING, remark

	# 0.3 QT applies only when short. Any plus amount is over filled.
	balance = tp_chhatni_balance_qt(tp_qty, cumulative_received, chhatni_kg_per_quintal)
	threshold = flt(CHHATNI_BALANCE_THRESHOLD_QT, 3)
	remark = _(
		"{0} Received − (TP + chhatni) is {1} QT. Shortfall threshold is {2} QT."
	).format(remark, flt(balance, 3), threshold)

	if balance > 0:
		return CHHATNI_OVER_FILLED, _(
			"{0} Received is above TP plus chhatni, so chhatni is over filled."
		).format(remark)

	if balance >= -threshold:
		return CHHATNI_RECEIVED, _(
			"{0} Shortfall is within {1} QT, so chhatni is received."
		).format(remark, threshold)

	return CHHATNI_NOT_RECEIVED, _(
		"{0} Shortfall is more than {1} QT, so chhatni is not received."
	).format(remark, threshold)


def grn_received_quantity(grn) -> float:
	entry_qty = sum(flt(row.entry_quantity) for row in (grn.entry_details or []))
	return flt(grn.net_weight) + entry_qty


def _sort_key(grn) -> tuple:
	receipt_dt = getattr(grn, "receipt_datetime", None)
	if receipt_dt:
		return (str(receipt_dt), grn.creation or "", grn.name or "")
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
			"receipt_datetime",
			"receipt_date",
			"receipt_time",
			"creation",
			"net_weight",
			"tp_quantity",
			"chhatni",
		],
		order_by="receipt_datetime asc, receipt_date asc, receipt_time asc, creation asc",
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
		cumulative = flt(cumulative + received, 3)

		tp_status = "In Progress"
		chhatni_status = ""
		chhatni_remark = ""

		if tp_qty > 0 and cumulative >= tp_qty:
			if not tp_completed_grn:
				tp_completed_grn = doc.name
			tp_status = "TP Completed"
			chhatni_status, chhatni_remark = evaluate_chhatni_fulfillment(
				tp_qty,
				cumulative,
				doc.chhatni,
			)
		elif tp_qty > 0 and cumulative < tp_qty:
			chhatni_status = CHHATNI_NOT_RECEIVED
			chhatni_remark = REMARK_TP_NOT_FILLED

		updates[doc.name] = {
			"received_quantity": received,
			"tp_cumulative_received": cumulative,
			"tp_chhatni_balance": tp_chhatni_balance_qt(tp_qty, cumulative, doc.chhatni),
			"tp_fulfillment_status": tp_status,
			"chhatni_fulfillment_status": chhatni_status,
			"chhatni_fulfillment_remark": chhatni_remark,
		}

	for name, values in updates.items():
		frappe.db.set_value("GRN Note", name, values, update_modified=False)


def clear_tp_fulfillment_fields(grn):
	grn.received_quantity = 0
	grn.tp_cumulative_received = 0
	grn.tp_chhatni_balance = 0
	grn.tp_fulfillment_status = ""
	grn.chhatni_fulfillment_status = ""
	grn.chhatni_fulfillment_remark = ""
