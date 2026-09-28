"""Sync Procurement workspace after GRN Note DocType was added."""

from ivri_od.patches.v1_0.sync_procurement_workspace_ui import execute as sync_procurement_workspace


def execute():
	sync_procurement_workspace()
