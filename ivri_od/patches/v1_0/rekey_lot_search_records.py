"""Lot Search: one record per lot (key "DC No., Lot No."), and the row's "Miller"
button (in the Print column) saved as PDF. The section had no key, so every
search saved its rows again as new records. Patches run before fixtures, so
the setting is made here too."""

import frappe

from ivri_od.procurement.portal_sync import rekey_section

SITE = "SCMS"
SECTION = "Lot Search"


def execute():
	if not frappe.db.exists("Portal Site", SITE):
		return
	site = frappe.get_doc("Portal Site", SITE)
	section = site.get_section(SECTION)
	if not section:
		return
	section.key_columns = section.key_columns or "DC No., Lot No."
	section.download_receipt = 1
	section.receipt_link_text = "Miller"
	site.save(ignore_permissions=True)
	rekey_section(SITE, SECTION)
