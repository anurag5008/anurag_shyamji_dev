# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""DCRO Paddy Release (Miller RO PDS) quantities per district.

The portal shows Paddy Lifted and Paddy Released for Milling of the mill's own district
and of other districts, e.g. "Paddy Lifted (Own District) (in Qtl)" and
"Quantity of Paddy Released for Milling (Other District)KORAPUT (in Qtl)". Own District
is the District of the mill in Mill Master; an other district is the word in the header
that is exactly a District Master name (case ignored). A header with no known district
keeps its portal name, e.g. "(Other District)".

Used by the Paddy Release from DCRO report (columns named per district, with a Remaining
Balance per district) and Stock Account for Paddy (Issue for Milling of one district)."""

import json
import re
from collections import defaultdict
from datetime import datetime

import frappe

# Paddy Lifted / Released headers; the number at the end tells apart headers seen twice ("... (in Qtl) 2").
DISTRICT_HEADER = re.compile(
	r"^(paddy lifted|quantity of paddy released for milling)\s*\((own|other) district\)\s*(.*?)\s*\(in qtl\)\s*(\d*)$",
	re.IGNORECASE,
)
DATE_COLUMN = "Date of Requistion"  # spelt as on the portal
SEASON_COLUMN = "Season"  # Kharif / Rabi of the page (Page Filter Columns "Season = #ddlseason")
KMS_COLUMN = "KMS Year"  # e.g. 2024-2025 (Page Filter Columns "KMS Year = #INTKMS")
SKIP_STATUS = ("reject", "cancel")  # these orders release nothing
LIFTED, RELEASED, BALANCE = "Paddy Lifted", "Paddy Released", "Remaining Balance"


def district_names() -> dict[str, str]:
	"""{name in lower case: District Master name}."""
	return {name.casefold(): name for name in frappe.get_all("District Master", pluck="name")}


def mill_districts() -> dict[str, str]:
	"""{mill: its District in Mill Master}."""
	return {
		row.name: row.district
		for row in frappe.get_all("Mill Master", filters={"district": ["is", "set"]}, fields=["name", "district"])
	}


def header_district(header: str, own_district: str | None, districts: dict[str, str]):
	"""(kind, district label) of a Paddy Lifted / Released header, kind "lifted" or "released";
	None for other headers. The label is the District Master name, else the portal's words,
	e.g. "(Other District)" ("(Other District) 2" for the second such pair)."""
	match = DISTRICT_HEADER.match((header or "").strip())
	if not match:
		return None
	kind = "lifted" if match.group(1).lower() == "paddy lifted" else "released"
	scope, text, number = match.group(2).lower(), match.group(3).strip(), match.group(4)
	district = own_district if scope == "own" else _known_district(text, districts)
	if district:
		return kind, district
	label = f"({scope.title()} District)" + (f" {text}" if text else "")
	return kind, label + (f" {number}" if number else "")


def _known_district(text: str, districts: dict[str, str]) -> str | None:
	"""The District Master name in the header text: the whole text, else one of its words."""
	if text.casefold() in districts:
		return districts[text.casefold()]
	for word in re.findall(r"[A-Za-z]+", text):
		if word.casefold() in districts:
			return districts[word.casefold()]
	return None


def released_by_district(cells: dict, own_district: str | None, districts: dict[str, str]) -> dict[str, float]:
	"""{district label: Paddy Released} of one row (0 for a rejected or cancelled order)."""
	out = defaultdict(float)
	cancelled = _cancelled(cells)
	for header, value in cells.items():
		found = header_district(header, own_district, districts)
		if found and found[0] == "released":
			out[found[1]] += 0.0 if cancelled else (_number(value) or 0.0)
	return dict(out)


def district_cells(records, cells_by_record: dict) -> dict:
	"""Report cells of each record: Paddy Lifted / Paddy Released named per district
	("Paddy Lifted Balangir"), each district's Released followed by its Remaining Balance.
	The balance runs over every saved row of the section (see remaining_balances)."""
	if not records:
		return cells_by_record
	districts, mills = district_names(), mill_districts()
	balances = remaining_balances(districts, mills, records[0].site, records[0].section)

	# Every row gets the same district block (districts in first-seen order) where its
	# first Paddy Lifted / Released column was, so rows read with other headers line up.
	split, labels = {}, []
	for record in records:
		own = mills.get(record.mill_id or "")
		before, quantities, after = {}, defaultdict(dict), {}
		for header, value in cells_by_record[record.name].items():
			found = header_district(header, own, districts)
			if not found:
				(after if quantities else before)[header] = value
				continue
			quantities[found[1]][found[0]] = value
			if found[1] not in labels:
				labels.append(found[1])
		split[record.name] = (before, quantities, after)

	out = {}
	for record in records:
		before, quantities, after = split[record.name]
		if not quantities:
			out[record.name] = cells_by_record[record.name]
			continue
		row_balance = balances.get(record.name) or {}
		cells = dict(before)
		for district in labels:
			cells[f"{LIFTED} {district}"] = quantities.get(district, {}).get("lifted", "")
			cells[f"{RELEASED} {district}"] = quantities.get(district, {}).get("released", "")
			balance = row_balance.get(district)
			cells[f"{BALANCE} {district}"] = "" if balance is None else f"{balance:.2f}"
		cells.update(after)
		out[record.name] = cells
	return out


def remaining_balances(districts=None, mills=None, site: str = "DCRO", section: str = "Paddy Release") -> dict:
	"""{record name: {district: Paddy Lifted - all Paddy Released of that district up to and
	including the row}}. Paddy Lifted is a running total on the portal; Released is added up
	per mill, KMS Year, Season (Kharif / Rabi) and district, in Date of Requistion then portal
	order (as the single Remaining Balance before, split by district, KMS Year and season)."""
	districts = districts if districts is not None else district_names()
	mills = mills if mills is not None else mill_districts()
	records = frappe.get_all(
		"Portal Record",
		filters={"site": site, "section": section},
		fields=["name", "row_data", "mill_id", "seen_run", "row_no"],
		order_by="seen_run asc, row_no asc",
		limit_page_length=0,
	)
	cells_by_record = {r.name: _load(r.row_data) for r in records}
	records.sort(key=lambda r: _date_key(cells_by_record[r.name].get(DATE_COLUMN)))

	released_so_far = defaultdict(float)  # (mill, KMS Year, Season, district)
	out = {}
	for record in records:
		cells = cells_by_record[record.name]
		own = mills.get(record.mill_id or "")
		# Each KMS Year's Kharif and Rabi have their own lifting: never one running total.
		group = (
			record.mill_id or "",
			"".join((cells.get(KMS_COLUMN) or "").split()),
			(cells.get(SEASON_COLUMN) or "").strip().casefold(),
		)
		for district, qty in released_by_district(cells, own, districts).items():
			released_so_far[(*group, district)] += qty
		balances = {}
		for header, value in cells.items():
			found = header_district(header, own, districts)
			lifted = _number(value) if found and found[0] == "lifted" else None
			if lifted is not None:
				balances[found[1]] = round(lifted - released_so_far[(*group, found[1])], 3)
		out[record.name] = balances
	return out


def _cancelled(cells: dict) -> bool:
	status = " ".join(v for h, v in cells.items() if "status" in h.lower()).lower()
	return any(word in status for word in SKIP_STATUS)


def _number(value):
	try:
		return float(str(value or "").replace(",", "").strip())
	except ValueError:
		return None


def _date_key(value) -> tuple:
	try:
		return (0, datetime.strptime((value or "").strip().replace("-", "/"), "%d/%m/%Y"))
	except ValueError:
		return (1, datetime.max)


def _load(raw) -> dict:
	try:
		value = json.loads(raw or "{}")
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}
