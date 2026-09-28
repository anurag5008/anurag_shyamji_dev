"""Reload Weigh Bridge Measurement after Sl No of QC field."""

from ivri_od.patches.v1_0.reload_quality_check_doctype import execute as reload_procurement_doctypes


def execute():
	reload_procurement_doctypes()
