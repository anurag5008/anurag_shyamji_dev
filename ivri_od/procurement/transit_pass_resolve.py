# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

import re

import frappe

_PPC_CODE_IN_PARENS = re.compile(r"^.+\(([^)]+)\)\s*$")


def matches_name_or_code(search_value: str | None, stored_value: str | None) -> bool:
	search_value = (search_value or "").strip().casefold()
	stored_value = (stored_value or "").strip().casefold()
	if not search_value or not stored_value:
		return False
	if search_value == stored_value:
		return True
	name, separator, code = stored_value.partition("(")
	if separator:
		code = code.rstrip(") ").strip()
		return search_value in {name.strip(), code}
	return False


def resolve_mill_master_name(
	pass_unique_key: str | None = None, miller: str | None = None
) -> str:
	"""Mill Master link name (miller_code) from pass key or PPAS miller text."""
	key = (pass_unique_key or "").strip()
	if key:
		row = frappe.db.get_value(
			"PPAS Transit Pass",
			{"pass_unique_key": key},
			["miller", "pass_unique_key"],
			as_dict=True,
		)
		if row:
			mill_id = mill_id_from_transit_pass(row)
			if mill_id and frappe.db.exists("Mill Master", mill_id):
				return mill_id
			miller = row.miller or miller

	text = (miller or "").strip()
	if not text:
		return ""

	mill_id = mill_id_from_transit_pass({"pass_unique_key": "", "miller": text})
	if mill_id and frappe.db.exists("Mill Master", mill_id):
		return mill_id

	if frappe.db.exists("Mill Master", text):
		return text

	found = frappe.db.get_value("Mill Master", {"company": text}, "name")
	return found or ""


def mill_id_from_transit_pass(row: dict) -> str:
	key = (row.get("pass_unique_key") or "").strip()
	if key:
		mill_code = key.partition("-")[0].strip()
		if mill_code:
			return mill_code
	miller = (row.get("miller") or "").strip()
	if not miller:
		return ""
	name, separator, code = miller.partition("(")
	if separator and code.rstrip(") ").strip():
		return code.rstrip(") ").strip()
	return miller


def resolve_ppc_master_name(ppc_text: str | None) -> str | None:
	ppc_text = (ppc_text or "").strip()
	if not ppc_text:
		return None

	paren = _PPC_CODE_IN_PARENS.match(ppc_text)
	if paren:
		code = paren.group(1).strip()
		found = frappe.db.get_value("PPC Master", {"code": code}, "name")
		if found:
			return found
		found = frappe.db.get_value("PPC Master", {"name": code}, "name")
		if found:
			return found

	for fieldname in ("name", "code", "ppc_name"):
		found = frappe.db.get_value("PPC Master", {fieldname: ppc_text}, "name")
		if found:
			return found

	rows = frappe.get_all(
		"PPC Master",
		fields=["name", "code", "ppc_name"],
		limit_page_length=5000,
	)
	for row in rows:
		for fieldname in ("name", "code", "ppc_name"):
			if matches_name_or_code(ppc_text, row.get(fieldname)):
				return row.name
	return None


def resolve_agent_master_name(agent_text: str | None) -> str | None:
	"""Link name for Agent Master (autoname = agent_name)."""
	agent_text = (agent_text or "").strip()
	if not agent_text:
		return None
	if frappe.db.exists("Agent Master", agent_text):
		return agent_text
	found = frappe.db.get_value("Agent Master", {"agent_name": agent_text}, "name")
	if found:
		return found
	for row in frappe.get_all("Agent Master", fields=["name", "agent_name"], limit_page_length=5000):
		if matches_name_or_code(agent_text, row.get("agent_name")) or matches_name_or_code(
			agent_text, row.get("name")
		):
			return row.name
	return None


def ensure_agent_master_link(agent_text: str | None) -> str | None:
	"""Agent Master link for WBM/GRN when party name is the agent (not a transit-pass PPC)."""
	link = resolve_agent_master_name(agent_text)
	if link:
		return link
	agent_text = (agent_text or "").strip()
	if not agent_text:
		return None
	try:
		doc = frappe.new_doc("Agent Master")
		doc.agent_name = agent_text
		doc.flags.ignore_permissions = True
		doc.insert()
		return doc.name
	except frappe.DuplicateEntryError:
		return resolve_agent_master_name(agent_text) or agent_text


def get_agent_for_ppc_text(rst_ppc_name: str | None, tp_ppc: str | None = None) -> str | None:
	for candidate in (rst_ppc_name, tp_ppc):
		ppc_link = resolve_ppc_master_name(candidate)
		if not ppc_link:
			continue
		agent = frappe.db.get_value("PPC Master", ppc_link, "agent")
		if agent:
			return agent
	return None


def party_name_exists_on_transit_pass(party_name: str | None) -> bool:
	"""True when Party Name matches the PPC value on any PPAS Transit Pass."""
	party_name = (party_name or "").strip()
	if not party_name:
		return False

	cache = getattr(frappe.local, "_party_on_transit_pass", None)
	if cache is None:
		cache = {}
		frappe.local._party_on_transit_pass = cache
	key = party_name.casefold()
	if key in cache:
		return cache[key]

	rows = frappe.get_all(
		"PPAS Transit Pass",
		fields=["ppc"],
		distinct=True,
		limit_page_length=0,
	)
	found = any(matches_name_or_code(party_name, row.get("ppc")) for row in rows)
	cache[key] = found
	return found


def find_transit_passes_by_tp_and_ppc(tp_no: str, ppc_name: str) -> list[dict]:
	tp_no = (tp_no or "").strip()
	ppc_name = (ppc_name or "").strip()
	if not tp_no or not ppc_name:
		return []

	rows = frappe.get_all(
		"PPAS Transit Pass",
		filters={"transit_pass_no": tp_no},
		fields=["pass_unique_key", "miller", "ppc", "transit_pass_no"],
		order_by="pass_unique_key asc",
		limit_page_length=1000,
	)
	return [row for row in rows if matches_name_or_code(ppc_name, row.ppc)]
