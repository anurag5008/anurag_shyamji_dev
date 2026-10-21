"""DCRO Paddy Release: one record per release order (key "RO No."). The section
had no key, so a changed row would have been saved again as a new record.
Patches run before fixtures, so the key is set here too."""

import frappe

from ivri_od.procurement.portal_sync import rekey_section

SITE = "DCRO"
SECTION = "Paddy Release"


def execute():
	if not frappe.db.exists("Portal Site", SITE):
		return
	site = frappe.get_doc("Portal Site", SITE)
	section = site.get_section(SECTION)
	if not section:
		return
	if not section.key_columns:
		section.key_columns = "RO No."
		site.save(ignore_permissions=True)
	rekey_section(SITE, SECTION)
