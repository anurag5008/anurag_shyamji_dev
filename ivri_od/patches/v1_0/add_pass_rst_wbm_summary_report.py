"""Install Pass RST WBM Summary script report and refresh Procurement desk."""

from ivri_od.procurement.procurement_workspace import sync_procurement_desk_ui


def execute():
	sync_procurement_desk_ui()
