# Copyright (c) 2026, Profezzo and contributors
"""Miller Verification Report: XI. Rice delivered during the week against DC (TOTAL) = FCI + RRC
on reports saved or submitted before the TOTAL was added, and its total over all columns.
Only the new fields are set; no other figure changes."""

import frappe
from frappe.utils import flt

PRECISION = 3


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabMiller Verification Agency`
		SET rice_delivered_week_total = ROUND(IFNULL(rice_delivered_week_fci, 0) + IFNULL(rice_delivered_week_rrc, 0), %s)
		WHERE parenttype = 'Miller Verification Report'
		""",
		PRECISION,
	)
	for report in frappe.get_all("Miller Verification Report", pluck="name"):
		total = frappe.db.sql(
			"""SELECT SUM(rice_delivered_week_total) FROM `tabMiller Verification Agency`
			WHERE parenttype = 'Miller Verification Report' AND parent = %s""",
			report,
		)[0][0]
		frappe.db.set_value(
			"Miller Verification Report",
			report,
			"total_rice_delivered_week_total",
			flt(total, PRECISION),
			update_modified=False,
		)
