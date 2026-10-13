"""Re-run for sites that missed Pass RST WBM Summary (report + desk shortcut)."""

from ivri_od.procurement.procurement_workspace import sync_procurement_desk_ui


def execute():
	sync_procurement_desk_ui()
