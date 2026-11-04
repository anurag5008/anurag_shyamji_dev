# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt
"""Milling Capacity Master: minimum paddy milled in a day (Qtl) for RAW and BOILED mills.

Used by Paddy Stock Register to spread a PVR's "Paddy Milled during the week" over the days of
that week: each day with milling gets at least this quantity."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

DEFAULT_MINIMUM = 400.0


class MillingCapacityMaster(Document):
	def validate(self):
		for fieldname in ("min_daily_milling_raw", "min_daily_milling_boiled"):
			if flt(self.get(fieldname)) < 0:
				frappe.throw(_("{0} cannot be negative").format(self.meta.get_label(fieldname)))


def get_min_daily_milling(mill_type: str | None) -> float:
	"""Minimum daily milling (Qtl) for a Mill Master Type (RAW / BOILED); 400 when not set."""
	fieldname = "min_daily_milling_boiled" if (mill_type or "").upper() == "BOILED" else "min_daily_milling_raw"
	value = flt(frappe.db.get_single_value("Milling Capacity Master", fieldname))
	return value if value > 0 else DEFAULT_MINIMUM
