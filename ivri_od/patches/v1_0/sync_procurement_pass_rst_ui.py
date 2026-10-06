"""Push Pass RST WBM report onto Procurement desk + sidebar (fixes missing UI links)."""

from ivri_od.procurement.procurement_workspace import sync_procurement_desk_ui


def execute():
	sync_procurement_desk_ui()
