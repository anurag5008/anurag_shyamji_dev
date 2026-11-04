# Copyright (c) 2026, Profezzo and contributors
"""Bag Management now belongs to ivri_od (it used to be the separate bag_management app).

Moves the owner of the "Bag Management" Module Def, Workspace, Workspace Sidebar and Desktop Icon to ivri_od, so that
uninstalling bag_management does not delete the module, its DocType, its report or any Gunny Bags Sent to PPC record.
Only rows still owned by bag_management are changed, so a rerun does nothing. No record is deleted or renamed and the
naming series is not touched."""

import frappe

MODULE = "Bag Management"
OLD_APP = "bag_management"
NEW_APP = "ivri_od"


def execute():
	if frappe.db.get_value("Module Def", MODULE, "app_name") == OLD_APP:
		frappe.db.set_value("Module Def", MODULE, "app_name", NEW_APP, update_modified=False)
	for doctype in ("Workspace", "Workspace Sidebar", "Desktop Icon"):
		if frappe.db.get_value(doctype, MODULE, "app") == OLD_APP:
			frappe.db.set_value(doctype, MODULE, "app", NEW_APP, update_modified=False)
	frappe.clear_cache()
