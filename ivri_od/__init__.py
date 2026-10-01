__version__ = "0.0.1"


def _patch_ivri_od():
	try:
		from ivri_od.workspace_report_links import patch_workspace_report_links

		patch_workspace_report_links()
	except Exception:
		pass


_patch_ivri_od()
