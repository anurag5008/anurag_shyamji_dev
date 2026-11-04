"""DCRO DC Transit Challan: one record per lot (key "DC Order No, Lot No."). Without a key a
row whose Pending At changed on the portal (e.g. "Manager QC Digital Sign" -> "Approved")
was saved as a new record, so the lot showed twice; the latest read is kept.
Patches run before fixtures, so the key is set here too."""

import frappe

from ivri_od.procurement.portal_sync import rekey_section

SITE = "DCRO"
SECTION = "DC Transit Challan"


def execute():
	if not frappe.db.exists("Portal Site", SITE):
		return
	site = frappe.get_doc("Portal Site", SITE)
	section = site.get_section(SECTION)
	if not section:
		return
	if not section.key_columns:
		section.key_columns = "DC Order No, Lot No."
		site.save(ignore_permissions=True)
	rekey_section(SITE, SECTION)
