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


def received_chhatni_pct(total_deduction: float, tp_qty: float) -> float:
	"""Chhatni % received on the TP = sum of deductions ÷ TP quantity × 100."""
	tp_qty = flt(tp_qty)
	if tp_qty <= 0:
		return 0.0
	return flt(flt(total_deduction) / tp_qty * 100, 2)


def tp_chhatni_balance_qt(tp_qty: float, cumulative_received: float, total_deduction: float) -> float:
	"""Pass total received − (TP quantity + sum of deductions).

	A negative result is kept as 0.
	"""
	tp_qty = flt(tp_qty)
	if tp_qty <= 0:
		return 0.0
	value = flt(cumulative_received) - tp_qty - flt(total_deduction)
	return flt(max(value, 0), 3)


def chhatni_fulfillment_status(
	tp_qty: float,
	cumulative_received: float,
	chhatni_kg_per_quintal: float,
	total_deduction: float = 0,
) -> str:
	status, _ = evaluate_chhatni_fulfillment(
		tp_qty,
		cumulative_received,
		chhatni_kg_per_quintal,
		total_deduction,
	)
	return status


def evaluate_chhatni_fulfillment(
	tp_qty: float,
	cumulative_received: float,
	chhatni_kg_per_quintal: float,
	total_deduction: float = 0,
) -> tuple[str, str]:
	tp_qty = flt(tp_qty)
	cumulative_received = flt(cumulative_received)
	chhatni_kg_per_quintal = flt(chhatni_kg_per_quintal)
	total_deduction = flt(total_deduction)

	if tp_qty <= 0 or cumulative_received < tp_qty:
		return CHHATNI_NOT_RECEIVED, REMARK_TP_NOT_FILLED

	required_qt = required_chhatni_qt(tp_qty, chhatni_kg_per_quintal)
	received_pct = received_chhatni_pct(total_deduction, tp_qty)
	gap = flt(total_deduction - required_qt, 3)

	remark = _(
		"Sum of deductions is {0} QT, which is {1}% of TP {2} QT. "
		"Required chhatni is {3} QT (TP × {4}% ÷ 100)."
	).format(
		flt(total_deduction, 3),
		flt(received_pct, 2),
		flt(tp_qty, 3),
		flt(required_qt, 3),
		flt(chhatni_kg_per_quintal, 2) if chhatni_kg_per_quintal > 0 else "—",
	)

	if chhatni_kg_per_quintal <= 0:
		return CHHATNI_PENDING, remark

	# 0.3 QT applies only when the deduction sum is short of required chhatni.
	threshold = flt(CHHATNI_BALANCE_THRESHOLD_QT, 3)
	if gap > 0:
		return CHHATNI_OVER_FILLED, _(
			"{0} Deduction sum is above the chhatni percentage, so chhatni is over filled."
		).format(remark)

	if gap >= -threshold:
		return CHHATNI_RECEIVED, _(
			"{0} Deduction sum meets the chhatni percentage, so chhatni is received."
		).format(remark)

	return CHHATNI_NOT_RECEIVED, _(
		"{0} Deduction sum is short of the chhatni percentage by more than {1} QT, so chhatni is not received."
	).format(remark, threshold)


def grn_received_quantity(grn) -> float:
	"""This GRN received = net weight + deduction + entry quantities."""
	entry_qty = sum(flt(row.entry_quantity) for row in (grn.entry_details or []))
	return flt(flt(grn.net_weight) + flt(grn.deduction) + entry_qty, 3)


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
	deduction_sum = 0.0
	tp_completed_grn: str | None = None
	updates: dict[str, dict] = {}

	for doc in grn_docs:
		received = grn_received_quantity(doc)
		cumulative = flt(cumulative + received, 3)
		deduction_sum = flt(deduction_sum + flt(doc.deduction), 3)

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
				deduction_sum,
			)
		elif tp_qty > 0 and cumulative < tp_qty:
			chhatni_status = CHHATNI_NOT_RECEIVED
			chhatni_remark = REMARK_TP_NOT_FILLED

		updates[doc.name] = {
			"received_quantity": received,
			"tp_cumulative_received": cumulative,
			"tp_chhatni_balance": tp_chhatni_balance_qt(tp_qty, cumulative, deduction_sum),
			"chhatni_received_pct": received_chhatni_pct(deduction_sum, tp_qty),
			"tp_cumulative_deduction": deduction_sum,
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
	grn.chhatni_received_pct = 0
	grn.tp_cumulative_deduction = 0
	grn.tp_fulfillment_status = ""
	grn.chhatni_fulfillment_status = ""
	grn.chhatni_fulfillment_remark = ""
