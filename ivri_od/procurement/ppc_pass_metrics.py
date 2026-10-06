# Copyright (c) 2026, Profezzo and contributors
"""Quantity rollups per transit pass and PPC for abstract reports."""

from __future__ import annotations

import re

import frappe
from frappe.utils import flt

from ivri_od.procurement.doctype.ppas_transit_pass.pass_unique_key import (
	miller_code_part,
	short_season_code,
)
from ivri_od.procurement.grn_tp_fulfillment import grn_received_quantity
from ivri_od.procurement.transit_pass_resolve import resolve_ppc_master_name


def build_pass_quantity_maps():
	"""Per pass_unique_key: physical net, GRN received, entry qty, TP qty."""
	physical_by_key: dict[str, float] = {}
	received_by_key: dict[str, float] = {}
	tp_qty_by_key: dict[str, float] = {}
	pacs_by_key: dict[str, str] = {}
	ppc_text_by_key: dict[str, str] = {}

	for grn in frappe.get_all(
		"GRN Note",
		filters={"docstatus": ["<", 2], "is_local_procurement": 0},
		fields=[
			"name",
			"pass_unique_key",
			"net_weight",
			"tp_quantity",
			"received_quantity",
			"ppc",
			"ppc_name",
			"pacs",
		],
	):
		key = (grn.pass_unique_key or "").strip()
		if not key:
			continue
		doc = frappe.get_doc("GRN Note", grn.name)
		received = flt(grn.received_quantity) or grn_received_quantity(doc)
		received_by_key[key] = received_by_key.get(key, 0) + received
		physical_by_key[key] = physical_by_key.get(key, 0) + flt(grn.net_weight)
		if flt(grn.tp_quantity):
			tp_qty_by_key[key] = max(tp_qty_by_key.get(key, 0), flt(grn.tp_quantity))
		ppc_text = (grn.ppc or grn.ppc_name or "").strip()
		if ppc_text:
			ppc_text_by_key.setdefault(key, ppc_text)
		pacs_text = (grn.pacs or "").strip()
		if pacs_text:
			pacs_by_key.setdefault(key, pacs_text)

	for tp in frappe.get_all(
		"PPAS Transit Pass",
		fields=["pass_unique_key", "name", "quantity", "pacs", "ppc"],
	):
		key = (tp.pass_unique_key or tp.name or "").strip()
		if not key:
			continue
		tp_qty_by_key[key] = max(tp_qty_by_key.get(key, 0), flt(tp.quantity))
		if tp.pacs:
			pacs_by_key[key] = (tp.pacs or "").strip()
		if tp.ppc:
			ppc_text_by_key[key] = (tp.ppc or "").strip()

	entry_by_key: dict[str, float] = {}
	for row in frappe.get_all("Entry", fields=["pass_unique_key", "entry_quantity"]):
		key = (row.pass_unique_key or "").strip()
		if not key:
			continue
		entry_by_key[key] = entry_by_key.get(key, 0) + flt(row.entry_quantity)

	_merge_wbm_net_into_pass_maps(physical_by_key, received_by_key, ppc_text_by_key)

	return {
		"physical_by_key": physical_by_key,
		"received_by_key": received_by_key,
		"entry_by_key": entry_by_key,
		"tp_qty_by_key": tp_qty_by_key,
		"pacs_by_key": pacs_by_key,
		"ppc_text_by_key": ppc_text_by_key,
	}


def _merge_wbm_net_into_pass_maps(
	physical_by_key: dict[str, float],
	received_by_key: dict[str, float],
	ppc_text_by_key: dict[str, str],
) -> None:
	"""Use WBM net when GRN is missing or lower (e.g. WBM saved before GRN / target allocation)."""
	wbm_net_by_key: dict[str, float] = {}
	for wbm in frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"is_farmer_or_agent": 0},
		fields=["pass_unique_key", "net_weight", "quality_test"],
	):
		if (wbm.quality_test or "").strip() == "Rejected":
			continue
		key = (wbm.pass_unique_key or "").strip()
		net = flt(wbm.net_weight)
		if not key or net <= 0:
			continue
		wbm_net_by_key[key] = wbm_net_by_key.get(key, 0) + net

	for key, wbm_net in wbm_net_by_key.items():
		if wbm_net > flt(physical_by_key.get(key)):
			physical_by_key[key] = wbm_net
		if wbm_net > flt(received_by_key.get(key)):
			received_by_key[key] = wbm_net
		if key not in ppc_text_by_key:
			ppc_text = _ppc_text_from_pass_unique_key(key)
			if ppc_text:
				ppc_text_by_key[key] = ppc_text


def effective_tp_quantity_for_pass(received: float, tp_qty: float) -> float:
	"""TP sum rule: full/over TP → count TP qty; else count physical received."""
	received = flt(received)
	tp_qty = flt(tp_qty)
	if tp_qty > 0 and received >= tp_qty:
		return tp_qty
	return received


def effective_tp_quantity_for_physical_abstract(
	entry_sum: float, received: float, tp_qty: float
) -> float:
	"""
	Abstract Physical TP column per transit pass.

	When Entry exists for the pass: if sum(entry) exceeds PPAS TP weight, count full TP;
	otherwise count the entry sum. With no Entry, use GRN received vs TP (legacy rule).
	"""
	entry_sum = flt(entry_sum)
	tp_qty = flt(tp_qty)
	if entry_sum > 0:
		if tp_qty > 0 and entry_sum > tp_qty:
			return tp_qty
		return entry_sum
	return effective_tp_quantity_for_pass(received, tp_qty)


def completed_quantity_for_pass(received: float, tp_qty: float) -> float:
	"""Mill–PPC abstract: capped at TP when weighing more than TP."""
	received = flt(received)
	tp_qty = flt(tp_qty)
	if tp_qty > 0:
		return min(received, tp_qty)
	return received


def ppc_link_for_pass_key(key: str, ppc_text_by_key: dict[str, str]) -> str | None:
	for candidate in (
		(ppc_text_by_key.get(key) or "").strip(),
		_ppc_text_from_pass_unique_key(key),
	):
		if not candidate:
			continue
		link = resolve_ppc_master_name(candidate)
		if link:
			return link
		if frappe.db.exists("PPC Master", candidate):
			return candidate
	return None


def _ppc_text_from_pass_unique_key(pass_unique_key: str) -> str:
	"""PPC segment from pass key, e.g. BAKTI(S1050104) from M051007-BAKTI(S1050104)-K25-TP45."""
	parts = (pass_unique_key or "").strip().split("-")
	if len(parts) < 4:
		return ""
	return "-".join(parts[1:-2]).strip()


def key_matches_mapping(key: str, mill_code: str, ppc_code: str, ppc_link: str, season_code: str) -> bool:
	parts = key.split("-")
	if len(parts) < 4:
		return False
	if mill_code and miller_code_part(parts[0]).casefold() != mill_code.casefold():
		return False
	if parts[-2].casefold() != season_code.casefold():
		return False
	ppc_part = "-".join(parts[1:-2])
	ppc_name = _ppc_name(ppc_link)
	if "(" in ppc_part and ppc_part.endswith(")"):
		name, code = ppc_part.rsplit("(", 1)
		code = code[:-1]
		return code.casefold() == (ppc_code or "").casefold() or _normalize(name) == _normalize(ppc_name)
	return _normalize(ppc_part) in {_normalize(ppc_link), _normalize(ppc_name), _normalize(ppc_code)}


def season_label(season, year):
	details = frappe.db.get_value("Season Master", season, ["crop_season", "year"], as_dict=True)
	if details:
		return f"{details.crop_season} {details.year}"
	return f"{season} {year or ''}".strip()


def mill_display_name(mill_link: str) -> str:
	if not mill_link:
		return ""
	company = frappe.db.get_value("Mill Master", mill_link, "company")
	if company:
		return (company or "").strip()
	return mill_link


def ppc_display_name(ppc_link: str) -> str:
	"""PPC label as name(code), for example BAKTI(S1050104)."""
	text = (ppc_link or "").strip()
	if not text:
		return ""

	row = _ppc_master_row(text)
	if not row and "(" in text and text.endswith(")"):
		name, code = text.rsplit("(", 1)
		code = code[:-1].strip()
		name = name.strip()
		row = _ppc_master_row(code) or _ppc_master_row(name)
		if not row:
			return f"{name}({code})" if name and code else text
	if not row:
		return text

	name = (row.ppc_name or "").strip()
	code = (row.code or "").strip()
	if name and code and f"({code})" not in name:
		return f"{name}({code})"
	return name or code or text


def _ppc_master_row(value: str):
	text = (value or "").strip()
	if not text or not frappe.db.table_exists("PPC Master"):
		return None
	if frappe.db.exists("PPC Master", text):
		return frappe.db.get_value("PPC Master", text, ["ppc_name", "code"], as_dict=True)
	return frappe.db.get_value("PPC Master", {"ppc_name": text}, ["ppc_name", "code"], as_dict=True) or frappe.db.get_value(
		"PPC Master", {"code": text}, ["ppc_name", "code"], as_dict=True
	)


def _ppc_name(ppc_link):
	return frappe.db.get_value("PPC Master", ppc_link, "ppc_name") or ppc_link


def _normalize(value):
	return re.sub(r"\s+", "", value or "").casefold()
