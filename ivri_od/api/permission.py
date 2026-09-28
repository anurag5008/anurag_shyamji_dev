# Copyright (c) 2026, Profezzo and contributors

import frappe


def has_app_permission() -> bool:
	"""Show ivri_od in the desk app switcher for users who can open Procurement."""
	if frappe.session.user == "Administrator":
		return True
	return bool(frappe.db.exists("DocType", "Gate Entry"))
