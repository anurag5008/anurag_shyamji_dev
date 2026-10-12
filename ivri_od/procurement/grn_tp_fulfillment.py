# Copyright (c) 2026, Profezzo and contributors
"""TP and Chhatni fulfillment status for government GRN (per Pass Unique Key)."""

from __future__ import annotations

import frappe
from frappe.utils import flt

CHHATNI_NOT_RECEIVED = "Chhatni Not Received"
CHHATNI_RECEIVED = "Chhatni Received"
CHHATNI_PENDING = "Chhatni Pending"
EXTRA_CHHATNI_RECEIVED = "Extra Chhatni Received"

# Allow shortfall vs required chhatni overfill (QT) when marking Chhatni Received.
CHHATNI_QT_TOLERANCE = 0.3


def chhatni_fulfillment_status(tp_qty: float, cumulative_received: float, chhatni_kg_per_quintal: float) -> str:
	"""
	Chhatni Received when overfill (cumulative - TP) reaches the chhatni allowance:
	required overfill QT = TP × (chhatni kg/qt ÷ 100), same as chhatni % of TP.
	Example: TP 206.69 QT, chhatni 9 → need ~18.6 QT overfill; 8.31 QT (~4%) → Pending.
	"""
	tp_qty = flt(tp_qty)
	cumulative_received = flt(cumulative_received)
	chhatni_kg_per_quintal = flt(chhatni_kg_per_quintal)
	if tp_qty <= 0 or cumulative_received < tp_qty:
		return ""
	if chhatni_kg_per_quintal <= 0:
		return "Chhatni Pending"
	overfill = flt(cumulative_received - tp_qty, 3)
	required_overfill = flt(tp_qty * chhatni_kg_per_quintal / 100, 3)
	if overfill + CHHATNI_QT_TOLERANCE >= required_overfill:
		return "Chhatni Received"
	return "Chhatni Pending"


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

		if tp_qty > 0 and cumulative >= tp_qty and not tp_completed_grn:
			tp_completed_grn = doc.name
			tp_status = "TP Completed"
			chhatni_status = chhatni_fulfillment_status(tp_qty, cumulative, doc.chhatni)

		updates[doc.name] = {
			"received_quantity": received,
			"tp_cumulative_received": cumulative,
			"tp_fulfillment_status": tp_status,
			"chhatni_fulfillment_status": chhatni_status,
		}

	for name, values in updates.items():
		frappe.db.set_value("GRN Note", name, values, update_modified=False)


def clear_tp_fulfillment_fields(grn):
	grn.received_quantity = 0
	grn.tp_cumulative_received = 0
	grn.tp_fulfillment_status = ""
	grn.chhatni_fulfillment_status = ""


def required_chhatni_qt(tp_qty: float, chhatni_percentage: float) -> float:
	"""Return the assigned chhatni quantity for a transit pass."""
	return flt(flt(tp_qty) * flt(chhatni_percentage) / 100, 3)


def received_chhatni_pct(total_deduction: float, tp_qty: float) -> float:
	"""Return deductions as a percentage of TP quantity."""
	tp_qty = flt(tp_qty)
	if tp_qty <= 0:
		return 0.0
	return flt(flt(total_deduction) / tp_qty * 100, 2)


def tp_chhatni_balance_qt(
	tp_qty: float, cumulative_received: float, total_deduction: float
) -> float:
	"""Return received quantity minus TP and recorded deductions."""
	return flt(flt(cumulative_received) - flt(tp_qty) - flt(total_deduction), 3)


def tp_fulfillment_status(tp_qty: float, cumulative_received: float) -> str:
	return "TP Completed" if flt(tp_qty) > 0 and flt(cumulative_received) >= flt(tp_qty) else "In Progress"


def remaining_tp_quantity(tp_qty: float, cumulative_received: float) -> float:
	return flt(max(flt(tp_qty) - flt(cumulative_received), 0), 3)


def pending_tp_quantity(tp_qty: float, cumulative_received: float) -> float:
	return remaining_tp_quantity(tp_qty, cumulative_received)


def excess_tp_received_quantity(tp_qty: float, cumulative_received: float) -> float:
	return flt(max(flt(cumulative_received) - flt(tp_qty), 0), 3)


def evaluate_chhatni_fulfillment(
	tp_qty: float,
	cumulative_received: float,
	chhatni_kg_per_quintal: float,
	total_deduction: float = 0,
) -> tuple[str, str]:
	"""Evaluate chhatni from GRN deductions for the Mandi Book report."""
	tp_qty = flt(tp_qty)
	if tp_qty <= 0 or flt(cumulative_received) < tp_qty:
		return CHHATNI_NOT_RECEIVED, ""
	if flt(chhatni_kg_per_quintal) <= 0:
		return CHHATNI_PENDING, ""
	actual_pct = received_chhatni_pct(total_deduction, tp_qty)
	assigned_pct = flt(chhatni_kg_per_quintal, 2)
	if actual_pct > assigned_pct + 0.30:
		return EXTRA_CHHATNI_RECEIVED, ""
	if actual_pct >= assigned_pct - 0.30:
		return CHHATNI_RECEIVED, ""
	return CHHATNI_PENDING, ""
