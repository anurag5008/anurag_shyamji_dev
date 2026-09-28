"""Let ivri_od desktop app icon open Procurement directly (no broken child modal)."""

from __future__ import annotations

import frappe

from ivri_od.patches.v1_0.setup_ivri_od_desk_app import (
	_ensure_procurement_workspace_title,
	_ensure_app_desktop_icon,
	_import_desktop_icons,
)


def execute():
	_ensure_procurement_workspace_title()
	_import_desktop_icons()
	_ensure_app_desktop_icon()
	frappe.clear_cache()
