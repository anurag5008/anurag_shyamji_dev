"""GRN Mill Name shows PPAS Transit Pass Miller text (not Mill Master link)."""

from ivri_od.patches.v1_0.grn_mill_chhatni_fields import _backfill_grn_mill_name_from_transit_pass

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "grn_note")
	_backfill_grn_mill_name_from_transit_pass()
	frappe.clear_cache()
