# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from ivri_od.procurement.doctype.local_paddy_purchase_order.local_paddy_purchase_order import (
	compute_po_status,
)


class TestLocalPaddyPurchaseOrder(FrappeTestCase):
	def test_po_status_computation(self):
		self.assertEqual(compute_po_status(100, 0), "Open")
		self.assertEqual(compute_po_status(100, 50), "Partially Received")
		self.assertEqual(compute_po_status(100, 100), "Completed")
		self.assertEqual(compute_po_status(100, 120), "Completed")
		self.assertEqual(compute_po_status(100, 50, "Closed"), "Closed")
