"""Fix Procurement desk sync (skip missing links) and Pass RST WBM UI visibility."""

from ivri_od.procurement.procurement_workspace import sync_procurement_desk_ui


def execute():
	sync_procurement_desk_ui()
