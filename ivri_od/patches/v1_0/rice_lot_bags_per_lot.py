"""Rice Lot Quantity: No. of Bags per Lot (580) for the Issue OSCSC of New NBT Gunny Account."""

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "rice_lot_quantity")
	if not frappe.db.get_single_value("Rice Lot Quantity", "bags_per_lot"):
		frappe.db.set_single_value("Rice Lot Quantity", "bags_per_lot", 580)
