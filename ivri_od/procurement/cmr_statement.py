# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Vehicle Wise Statement for CMR (rice delivery): the rows of the statement from the portal data.

FCI: DC Transit Challan from DCRO (Portal Record, DCRO / DC Transit Challan), one row per challan. A challan
with two vehicles ("OD31P9471 ,OD31P9499") is split into one row per vehicle: bags and quintal are divided
by the number of vehicles and every other detail is copied (580 bags become 290 + 290).
RRC: Lot Search from SCMS (Portal Record, SCMS / Lot Search), one row per lot; its Vehicle No is read from the lot's PDF
(a lot with two vehicles is split like an FCI challan).

The season (Kharif(2025)) is read as the KMS year 2025-26 and the crop season Kharif: a DC belongs to the
season when its KMS Year starts with 2025 and View DC from DCRO gives it the Season KHARIF."""

import json
import re

import frappe
from frappe.utils import flt, getdate

from ivri_od.procurement import vehicle_statement as vs

FCI = "FCI"
RRC = "RRC"
SITE_FCI, SECTION_FCI = "DCRO", "DC Transit Challan"
SITE_RRC, SECTION_RRC = "SCMS", "Lot Search"
SITE_VIEW, SECTION_VIEW = "DCRO", "View DC"


def parse_season(season):
	"""'Kharif(2025)' or 'Kharif 2025' gives ('kharif', '2025'); ('', '') when it cannot be read."""
	match = re.match(r"\s*([A-Za-z]+)\s*[\(\s-]*\s*(\d{4})", season or "")
	return (match.group(1).lower(), match.group(2)) if match else ("", "")


def split_vehicles(text):
	"""'OD31P9471 ,OD31P9499' gives ['OD31P9471', 'OD31P9499']; the vehicle numbers are kept as written (spaces removed)."""
	parts = [vs.normal_vehicle(part) for part in re.split(r"[,/&+;]|\band\b", text or "", flags=re.I)]
	return [part for part in parts if part]


def _cells(record):
	try:
		return json.loads(record.row_data or "{}") or {}
	except ValueError:
		return {}


def _records(site, section, mill_code=None):
	filters = {"site": site, "section": section}
	if mill_code:
		filters["mill_id"] = mill_code
	return frappe.get_all("Portal Record", filters=filters, fields=["mill_id", "row_data"], limit_page_length=0)


def _date(text):
	"""'20-06-2026' or '20/06/2026' gives a date; None when it is empty or not a date."""
	text = (text or "").strip()
	if not text:
		return None
	try:
		return getdate(text.replace("/", "-"), parse_day_first=True)
	except Exception:
		return None


def _number(text):
	return flt(str(text or "").replace(",", ""))


def season_of_dcs():
	"""{DC code: season in lower case} from View DC from DCRO."""
	seasons = {}
	for record in _records(SITE_VIEW, SECTION_VIEW):
		cells = _cells(record)
		code = (cells.get("DC Code(RRC)") or "").strip()
		if code:
			seasons[code] = (cells.get("Season") or "").strip().lower()
	return seasons


def millers(cmr_to):
	"""'MILLER NAME (CODE)' of the millers in the portal data of FCI or RRC, to choose from."""
	found = {}
	if cmr_to == RRC:
		for record in _records(SITE_RRC, SECTION_RRC):
			code = (record.mill_id or "").strip()
			if code and code not in found:
				company = frappe.db.get_value("Mill Master", code, "company") or ""
				found[code] = f"{company.strip()} ({code})" if company else code
	else:
		for record in _records(SITE_FCI, SECTION_FCI):
			cells = _cells(record)
			code = (cells.get("MillerCode") or record.mill_id or "").strip()
			name = (cells.get("Miller Name") or "").strip()
			if code and code not in found:
				found[code] = f"{name} ({code})" if name else code
	return sorted(found.values())


def mill_code_of(miller):
	"""'SHREE SHYAMJI PADDY PROCESSING PVT LTD (M051007)' gives 'M051007'."""
	match = re.search(r"\(([^)]+)\)\s*$", miller or "")
	return (match.group(1) if match else (miller or "")).strip()


def fci_rows(miller, season):
	"""One row per challan and vehicle of the Miller and Season (accepted challans only)."""
	crop, year = parse_season(season)
	code = mill_code_of(miller)
	seasons = season_of_dcs()
	rows = []
	for record in _records(SITE_FCI, SECTION_FCI, code):
		cells = _cells(record)
		if year and not (cells.get("KMS Year") or "").strip().startswith(year):
			continue
		if crop and seasons.get((cells.get("DC Order No") or "").strip()) != crop:
			continue
		accepted = _date(cells.get("Accepted Date"))
		if not accepted:
			continue  # a challan that is not accepted yet is not delivered
		vehicles = split_vehicles(cells.get("Vechicle No.")) or [""]
		share = len(vehicles)
		bags = round(_number(cells.get("No. of Bags(In kg.)")) / share)
		qty = flt(_number(cells.get("Net Weight")) / share, 3)
		for vehicle in vehicles:
			rows.append(
				{
					"challan_date": accepted,
					"depo_name": (cells.get("Depot Name") or "").strip(),
					"depot_code": (cells.get("Depot Code") or "").strip(),
					"lot_no": (cells.get("Lot No.") or "").strip(),
					"vehicle_no": vehicle,
					"ac_note_no": (cells.get("Acceptance Note No") or "").strip(),
					"bags": bags,
					"qty": qty,
				}
			)
	rows.sort(key=lambda row: (row["vehicle_no"], row["challan_date"], row["lot_no"]))
	return rows


def rrc_rows(miller, season):
	"""One row per accepted lot (and vehicle) of the Miller and Season from Lot Search (SCMS)."""
	crop, year = parse_season(season)
	code = mill_code_of(miller)
	seasons = season_of_dcs()
	rows = []
	for record in _records(SITE_RRC, SECTION_RRC, code):
		cells = _cells(record)
		if year and not (cells.get("KMS Year") or "").strip().startswith(year):
			continue
		if crop and seasons.get((cells.get("DC No.") or "").strip()) != crop:
			continue
		if (cells.get("Challan Status") or "").strip().lower() != "accepted":
			continue
		depot = (cells.get("Depot") or "").strip()  # 'DW051105-Malmunda'
		depot_code, _, depot_name = depot.partition("-")
		vehicles = split_vehicles(cells.get("Vehicle No")) or [""]  # read from the lot's PDF; "" when it is not read yet
		bags = round(_number(cells.get("No.of Bag")) / len(vehicles))
		qty = flt(_number(cells.get("Qty(In Qtl.)")) / len(vehicles), 3)
		for vehicle in vehicles:
			rows.append(
				{
					"challan_date": _date(cells.get("Receipt Date")) or _date(cells.get("Transit Challan Date")),
					"depo_name": (depot_name or depot).strip(),
					"depot_code": depot_code.strip() if depot_name else "",
					"lot_no": (cells.get("Lot No.") or "").strip(),
					"vehicle_no": vehicle,
					"ac_note_no": (cells.get("A.C. Note No.") or "").strip(),
					"bags": bags,
					"qty": qty,
				}
			)
	rows.sort(key=lambda row: (row["vehicle_no"], row["challan_date"] or getdate("1900-01-01"), row["lot_no"]))
	return rows


def cmr_rows(cmr_to, miller, season):
	return rrc_rows(miller, season) if cmr_to == RRC else fci_rows(miller, season)


def depo_distances(codes):
	"""{Depo code: Distance (KM)} of the Depo Master records that have one."""
	codes = [c for c in set(codes) if c]
	if not codes:
		return {}
	rows = frappe.get_all("Depo Master", filters={"code": ["in", codes]}, fields=["code", "distance"])
	return {row.code: flt(row.distance, 1) for row in rows if flt(row.distance)}
