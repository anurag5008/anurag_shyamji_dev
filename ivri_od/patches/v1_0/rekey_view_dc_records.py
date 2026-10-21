"""DCRO View DC: one record per DC (key "DC Code(RRC)"), titled by its DC code.
Patches run before fixtures, so the key is set here too."""

import frappe

from ivri_od.procurement.portal_sync import rekey_section

SITE = "DCRO"
SECTION = "View DC"


def execute():
	if not frappe.db.exists("Portal Site", SITE):
		return
	site = frappe.get_doc("Portal Site", SITE)
	section = site.get_section(SECTION)
	if not section:
		return
	if not section.key_columns:
		section.key_columns = "DC Code(RRC)"
		site.save(ignore_permissions=True)
	rekey_section(SITE, SECTION)
