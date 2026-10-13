"""Add Manual PPAS Import to Procurement desk shortcuts and sidebar."""

from ivri_od.procurement.procurement_workspace import ensure_procurement_workspace_after_migrate


def execute():
	ensure_procurement_workspace_after_migrate()
