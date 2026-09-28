# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import re

import frappe

MAX_KEY_LENGTH = 140

_MILLER_CODE_RE = re.compile(r"\b(M\d+)\b", re.IGNORECASE)
_PPC_WITH_CODE_RE = re.compile(r"^(.+)\(([^)]+)\)$")


def _key_part(value, fallback="UNKNOWN"):
	text = (value or "").strip() or fallback
	text = re.sub(r"[/\\]", "-", text)
	return text


def short_season_code(season):
	"""Kharif 2025 -> K25, Rabi 2024 -> R24; passes through existing K25/R24."""
	text = (season or "").strip()
	if not text:
		return "S00"

	short = re.match(r"^([KR])(\d{2})$", text, re.IGNORECASE)
	if short:
		return short.group(1).upper() + short.group(2)

	season_lower = text.lower()
	prefix = ""
	if "kharif" in season_lower:
		prefix = "K"
	elif "rabi" in season_lower:
		prefix = "R"

	year_match = re.search(r"(\d{4})", text)
	if year_match:
		yy = year_match.group(1)[-2:]
	elif prefix:
		inline = re.search(r"[KR](\d{2})\b", text, re.IGNORECASE)
		yy = inline.group(1) if inline else "00"
	else:
		return _key_part(text, "S00")

	if not prefix:
		inline = re.match(r"^([KR])(\d{2})\b", text, re.IGNORECASE)
		if inline:
			return inline.group(1).upper() + inline.group(2)
		return _key_part(text, "S00")

	return prefix + yy


def miller_code_part(miller):
	text = (miller or "").strip()
	if not text:
		return "UNKNOWN"
	match = _MILLER_CODE_RE.search(text)
	if match:
		return match.group(1).upper()
	first = text.split()[0]
	return _key_part(first)


def ppc_key_part(ppc):
	text = (ppc or "").strip()
	if not text:
		return "UNKNOWN"

	existing = _PPC_WITH_CODE_RE.match(text)
	if existing:
		name = existing.group(1).strip()
		code = existing.group(2).strip()
		return f"{_key_part(name)}({_key_part(code, 'UNKNOWN')})"

	if frappe.db.table_exists("PPC Master"):
		code = frappe.db.get_value("PPC Master", {"ppc_name": text}, "code")
		if code:
			return f"{_key_part(text)}({_key_part(code)})"
		row = frappe.db.get_value(
			"PPC Master", {"code": text}, ["ppc_name", "code"], as_dict=True
		)
		if row and row.ppc_name:
			return f"{_key_part(row.ppc_name)}({_key_part(row.code or text)})"

	return _key_part(text)


def transit_pass_key_part(transit_pass_no):
	text = _key_part(transit_pass_no)
	if text == "UNKNOWN":
		return text
	upper = text.upper()
	if upper.startswith("TP"):
		return "TP" + text[2:]
	return f"TP{text}"


def make_pass_unique_key(transit_pass_no, ppc, miller=None, season=None):
	"""Format: {miller_code}-{ppc_name(ppc_code)}-{K|R}{YY}-TP{transit_pass_no}."""
	key = "-".join(
		[
			miller_code_part(miller),
			ppc_key_part(ppc),
			short_season_code(season),
			transit_pass_key_part(transit_pass_no),
		]
	)
	return key[:MAX_KEY_LENGTH]
