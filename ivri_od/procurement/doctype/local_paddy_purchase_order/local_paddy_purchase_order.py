# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate


def get_po_received_quantity(po_name: str) -> float:
	"""Calculate cumulative received quantity from actual downstream GRN Notes."""
	if not po_name:
		return 0.0

	res = frappe.db.sql(
		"""
		SELECT IFNULL(SUM(net_weight), 0)
		FROM `tabGRN Note`
		WHERE (local_purchase_order = %s OR purchase_order = %s)
		  AND is_local_procurement = 1
		  AND docstatus < 2
		""",
		(po_name, po_name),
	)
	return flt(res[0][0]) if res else 0.0


def compute_po_status(ordered_qty: float, received_qty: float, current_status: str | None = None) -> str:
	if current_status == "Closed":
		return "Closed"
	if flt(ordered_qty) <= 0:
		return "Draft"
	if flt(received_qty) <= 0:
		return "Open"
	if flt(received_qty) < flt(ordered_qty):
		return "Partially Received"
	return "Completed"


class LocalPaddyPurchaseOrder(Document):
	def validate(self):
		self._normalize_fields()
		self._validate_ordered_quantity()
		self._compute_quantities_and_status()

	def _normalize_fields(self):
		if self.party_name:
			self.party_name = self.party_name.strip()
		if self.commodity:
			self.commodity = self.commodity.strip()
		if not self.order_date:
			self.order_date = nowdate()

	def _validate_ordered_quantity(self):
		if flt(self.ordered_quantity) <= 0:
			frappe.throw(_("Ordered Quantity must be greater than zero."))

	def _compute_quantities_and_status(self):
		if not self.is_new() and self.name:
			self.received_quantity = get_po_received_quantity(self.name)
		else:
			self.received_quantity = flt(self.received_quantity)

		self.pending_quantity = max(flt(self.ordered_quantity) - flt(self.received_quantity), 0.0)
		self.status = compute_po_status(self.ordered_quantity, self.received_quantity, self.status)


def update_purchase_order_quantities(po_name: str):
	"""Sync PO received and pending quantities from valid GRN Notes."""
	if not po_name or not frappe.db.exists("Local Paddy Purchase Order", po_name):
		return

	po = frappe.get_doc("Local Paddy Purchase Order", po_name)
	recv = get_po_received_quantity(po_name)
	pending = max(flt(po.ordered_quantity) - recv, 0.0)
	status = compute_po_status(po.ordered_quantity, recv, po.status)

	frappe.db.set_value(
		"Local Paddy Purchase Order",
		po_name,
		{
			"received_quantity": recv,
			"pending_quantity": pending,
			"status": status,
		},
		update_modified=False,
	)


@frappe.whitelist()
def refresh_po_quantities(po_name: str) -> dict:
	update_purchase_order_quantities(po_name)
	return frappe.db.get_value(
		"Local Paddy Purchase Order",
		po_name,
		["name", "ordered_quantity", "received_quantity", "pending_quantity", "status"],
		as_dict=True,
	) or {}


@frappe.whitelist()
def get_open_purchase_orders_for_party(party_name: str) -> list[dict]:
	"""Return open / partially received POs for a given party name."""
	party = (party_name or "").strip()
	if not party:
		return []

	# Search by exact or substring match
	return frappe.get_all(
		"Local Paddy Purchase Order",
		filters={
			"party_name": ["like", f"%{party}%"],
			"status": ["in", ["Open", "Partially Received"]],
		},
		fields=[
			"name",
			"party_name",
			"order_date",
			"commodity",
			"ordered_quantity",
			"received_quantity",
			"pending_quantity",
			"status",
		],
		order_by="order_date desc, creation desc",
	)


@frappe.whitelist()
def close_purchase_order(po_name: str):
	doc = frappe.get_doc("Local Paddy Purchase Order", po_name)
	doc.status = "Closed"
	doc.save(ignore_permissions=True)
	return {"status": doc.status}


@frappe.whitelist()
def reopen_purchase_order(po_name: str):
	doc = frappe.get_doc("Local Paddy Purchase Order", po_name)
	doc.status = compute_po_status(doc.ordered_quantity, doc.received_quantity, None)
	doc.save(ignore_permissions=True)
	return {"status": doc.status}
