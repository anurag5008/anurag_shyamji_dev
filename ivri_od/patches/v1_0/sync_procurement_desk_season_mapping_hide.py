"""Hide Season Mapping desk links; ensure Pass RST WBM report on Procurement UI."""

from ivri_od.procurement.procurement_workspace import sync_procurement_desk_ui


def execute():
	sync_procurement_desk_ui()
