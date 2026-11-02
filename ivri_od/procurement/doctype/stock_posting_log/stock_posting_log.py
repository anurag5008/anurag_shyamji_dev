# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class StockPostingLog(Document):
	"""One row per GRN Note posting. Created by ivri_od.procurement.stock_posting only."""
