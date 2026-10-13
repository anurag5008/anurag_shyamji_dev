"""Chhatni Not Received when TP open; clearer pass-total labels; chhatni note field."""

import frappe

from ivri_od.patches.v1_0.recalc_grn_chhatni_fulfillment import execute as recalc_tp_chhatni


def execute():
	frappe.reload_doc("procurement", "doctype", "grn_note")
	recalc_tp_chhatni()
