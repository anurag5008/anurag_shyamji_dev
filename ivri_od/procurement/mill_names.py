# Copyright (c) 2026, Profezzo and contributors
"""Short Name of a mill (Mill Master) for lists and reports.

The client wants to see the Short Name (SSPPB) and not the full name (SHREE SHYAMJI PADDY PROCESSING PVT LTD (Boiled))."""

import re

import frappe


def _short_name_map() -> dict[str, str]:
	"""{mill code / company, lower case: Short Name}, read once per request."""
	cached = getattr(frappe.local, "mill_short_name_map", None)
	if cached is not None:
		return cached
	mapping: dict[str, str] = {}
	for row in frappe.get_all("Mill Master", fields=["name", "miller_code", "company", "short_name"]):
		short = (row.short_name or "").strip()
		if not short:
			continue
		for key in (row.name, row.miller_code, row.company):
			if (key or "").strip():
				mapping[key.strip().casefold()] = short
	frappe.local.mill_short_name_map = mapping
	return mapping


def mill_short_name(value: str | None) -> str:
	"""Short Name for a mill code ("M051007"), a name with its code ("SHREE ... (M051007)") or a company name.

	Returns the value itself when the mill has no Short Name (or is not found)."""
	text = (value or "").strip()
	if not text:
		return ""
	mapping = _short_name_map()
	code = re.search(r"\(([^)]+)\)\s*$", text)
	for candidate in ((code.group(1) if code else ""), text):
		short = mapping.get(candidate.strip().casefold())
		if short:
			return short
	return text
