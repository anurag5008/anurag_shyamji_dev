# Copyright (c) 2026, Profezzo and contributors
"""Keep hidden Procurement reports off the sidebar boot payload."""

from __future__ import annotations

from ivri_od.procurement.procurement_workspace import (
	PASS_RST_QUERY_URL,
	PASS_RST_REPORT,
	PASS_RST_SIDEBAR_LABEL,
)

_HIDDEN_LABELS = {PASS_RST_SIDEBAR_LABEL, "Chhatni Tracking"}
_HIDDEN_LINKS = {PASS_RST_REPORT, "Chhatni Tracking"}
_HIDDEN_URLS = (PASS_RST_QUERY_URL, "/app/query-report/Chhatni%20Tracking")


def extend_procurement_boot(bootinfo):
	"""Drop hidden report links if a stale sidebar still carries them."""
	sidebars = bootinfo.get("workspace_sidebar_item") or {}
	proc = sidebars.get("procurement")
	if not proc:
		return

	proc["items"] = [item for item in (proc.get("items") or []) if not _is_hidden_sidebar_item(item)]
	sidebars["procurement"] = proc
	bootinfo["workspace_sidebar_item"] = sidebars


def _is_hidden_sidebar_item(item: dict) -> bool:
	url = (item.get("url") or "").strip()
	label = (item.get("label") or "").strip()
	link_to = (item.get("link_to") or "").strip()
	if label in _HIDDEN_LABELS or link_to in _HIDDEN_LINKS:
		return True
	return any(piece in url for piece in _HIDDEN_URLS)
