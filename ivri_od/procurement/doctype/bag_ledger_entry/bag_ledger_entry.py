# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class BagLedgerEntry(Document):
	"""Append-only bag count per warehouse / item / batch. Written by ivri_od.procurement.inventory_foundation."""
