# Copyright (c) 2026, Profezzo and contributors
"""Purchase Receipt: the Rate is copied from the Purchase Order and the user may change it.

Buying Settings "Maintain Same Rate Throughout the Purchase Cycle" stops any change of the Rate after the order, so it is switched off.
Only this one setting is changed."""

import frappe


def execute():
	frappe.db.set_single_value("Buying Settings", "maintain_same_rate", 0)
	frappe.clear_cache()
