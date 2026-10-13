# Copyright (c) 2026, Profezzo and contributors
"""TP and Chhatni fulfillment status for government GRN (per Pass Unique Key)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

CHHATNI_NOT_RECEIVED = "Chhatni Not Received"
CHHATNI_PENDING = "Chhatni Pending"
CHHATNI_RECEIVED = "Chhatni Received"
EXTRA_CHHATNI_RECEIVED = "Extra Chhatni Received"
# Kept for backward compatibility if imported elsewhere
CHHATNI_OVER_FILLED = EXTRA_CHHATNI_RECEIVED
# Chhatni tolerance in percentage points (0.30% point).
CHHATNI_TOLERANCE_PCT = 0.30

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


def tp_fulfillment_status(tp_qty: float, cumulative_net_received: float) -> str:
	"""Canonical TP fulfillment status based on cumulative final net weight received."""
	if flt(tp_qty) > 0 and flt(cumulative_net_received) >= flt(tp_qty):
		return "TP Completed"
	return "In Progress"


def remaining_tp_quantity(tp_qty: float, cumulative_net_received: float) -> float:
	"""Remaining TP quantity = max(tp_quantity - cumulative_net_received, 0)."""
	tp_qty = flt(tp_qty)
	cumulative = flt(cumulative_net_received)
	if tp_qty <= 0:
		return 0.0
	return flt(max(tp_qty - cumulative, 0.0), 3)


def pending_tp_quantity(tp_qty: float, cumulative_net_received: float) -> float:
	"""Pending TP quantity = max(tp_quantity - cumulative_net_received, 0)."""
	return remaining_tp_quantity(tp_qty, cumulative_net_received)


def excess_tp_received_quantity(tp_qty: float, cumulative_net_received: float) -> float:
	"""Excess received quantity = max(cumulative_net_received - tp_qty, 0)."""
	tp_qty = flt(tp_qty)
	cumulative = flt(cumulative_net_received)
	if cumulative <= tp_qty:
		return 0.0
	return flt(max(cumulative - tp_qty, 0.0), 3)


def calculate_chhatni_metrics(
	tp_qty: float,
	cumulative_received: float = 0,
	chhatni_kg_per_quintal: float = 0,
	total_deduction: float = 0,
) -> dict:
	"""Canonical Chhatni calculation and status evaluation."""
	tp_qty = flt(tp_qty)
	cumulative_received = flt(cumulative_received)
	chhatni_rate = flt(chhatni_kg_per_quintal)
	total_deduction = flt(total_deduction)

	required_qt = required_chhatni_qt(tp_qty, chhatni_rate)
	actual_pct = received_chhatni_pct(total_deduction, tp_qty)
	assigned_pct = flt(chhatni_rate, 2)
	deviation_pct = flt(actual_pct - assigned_pct, 2)
	tolerance_pct = flt(CHHATNI_TOLERANCE_PCT, 2)

	if tp_qty <= 0:
		status = CHHATNI_NOT_RECEIVED
		remark = _("Transit pass (TP) quantity is missing or zero.")
	elif chhatni_rate <= 0:
		status = CHHATNI_PENDING
		remark = _(
			"Sum of deductions is {0} QT, which is {1}% of TP {2} QT. "
			"Assigned chhatni rate is not set."
		).format(flt(total_deduction, 3), flt(actual_pct, 2), flt(tp_qty, 3))
	else:
		base_remark = _(
			"Sum of deductions is {0} QT, which is {1}% of TP {2} QT. "
			"Required chhatni is {3} QT (TP × {4}% ÷ 100)."
		).format(
			flt(total_deduction, 3),
			flt(actual_pct, 2),
			flt(tp_qty, 3),
			flt(required_qt, 3),
			flt(assigned_pct, 2),
		)
		lower_bound = flt(assigned_pct - tolerance_pct, 4)
		upper_bound = flt(assigned_pct + tolerance_pct, 4)
		actual_compare = flt(actual_pct, 4)

		if actual_compare > upper_bound + 1e-6:
			status = EXTRA_CHHATNI_RECEIVED
			remark = _(
				"{0} Deduction percentage ({1}%) exceeds assigned chhatni ({2}%) by more than {3} percentage points, so extra chhatni is received."
			).format(base_remark, flt(actual_pct, 2), flt(assigned_pct, 2), tolerance_pct)
		elif actual_compare >= lower_bound - 1e-6:
			status = CHHATNI_RECEIVED
			remark = _(
				"{0} Deduction percentage ({1}%) is within ±{2} percentage points of assigned chhatni ({3}%), so chhatni is received."
			).format(base_remark, flt(actual_pct, 2), tolerance_pct, flt(assigned_pct, 2))
		else:
			status = CHHATNI_NOT_RECEIVED
			remark = _(
				"{0} Deduction percentage ({1}%) is below assigned chhatni ({2}%) by more than {3} percentage points, so chhatni is not received."
			).format(base_remark, flt(actual_pct, 2), flt(assigned_pct, 2), tolerance_pct)

	return {
		"tp_quantity": tp_qty,
		"assigned_chhatni_kg_per_qtl": chhatni_rate,
		"assigned_chhatni_pct": assigned_pct,
		"required_chhatni_qtl": required_qt,
		"cumulative_deduction_qtl": total_deduction,
		"actual_chhatni_percent": actual_pct,
		"deviation_percent": deviation_pct,
		"tolerance_percent": tolerance_pct,
		"status": status,
		"remark": remark,
	}


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
	metrics = calculate_chhatni_metrics(
		tp_qty,
		cumulative_received,
		chhatni_kg_per_quintal,
		total_deduction,
	)
	return metrics["status"], metrics["remark"]


def grn_received_quantity(grn) -> float:
	"""Final net weight received for this GRN."""
	if not grn:
		return 0.0
	if isinstance(grn, dict):
		return flt(grn.get("net_weight") or 0.0, 3)
	return flt(getattr(grn, "net_weight", 0) or 0.0, 3)


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

		tp_status = tp_fulfillment_status(tp_qty, cumulative)
		if tp_status == "TP Completed" and not tp_completed_grn:
			tp_completed_grn = doc.name

		doc_chhatni = flt(doc.chhatni) or max((flt(r.chhatni) for r in rows), default=0.0)
		chhatni_status, chhatni_remark = evaluate_chhatni_fulfillment(
			tp_qty,
			cumulative,
			doc_chhatni,
			deduction_sum,
		)

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
