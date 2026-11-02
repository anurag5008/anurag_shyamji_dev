# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Gunny Bags Ledger rules: pure Python, no database access.

One row per Mill + PPC.

Credit Bags and Qty come from completed trips. A trip is one Weigh Bridge Measurement (WBM) and is completed only
when that WBM links a Quality Check that exists (WBM.quality_check) AND a GRN Note links back to it
(GRN Note.weigh_bridge_measurement). Nothing is matched by the Pass Unique Key alone.
- Qty = sum of WBM net_weight (QT) over completed trips.
- Credit Bags = sum, over completed trips, of the physical bag count of the trip's own Quality Check
  (Quality Check "Paddy Received (Bags)", the total of its Jute / Plastic bag rows). The weighment's Transit Pass
  bag count is not used: it repeats the whole pass on every trip.
- Each WBM is counted once, however many GRN Notes point to it. Two WBMs that share a Quality Check are two trips,
  and each adds that Quality Check's bags.

Debit Bags = sum of "Number of Bags Sent" of the submitted Gunny Bags Sent to PPC records of that Mill + PPC.
The mill and PPC of a Transit Pass are matched to the masters, so the sent bags of one PPC are counted once on its
single row however many Transit Passes it has. A PPC with sent bags but no completed trip still gets a row.
A Transit Pass whose PPC or mill is not in the masters is grouped by its own text and has no Debit Bags.

Remaining Bags = Debit Bags - Credit Bags of the row: the gunny bags sent to the PPC that have not come back with
paddy. It is filled only on a row that has Debit Bags, and is never negative: when as many bags or more came back
than were sent, it shows 0. On a row with no Debit Bags it is left empty.

Mill Name is the full name of the selected Mill Master on every row (not the Transit Pass text).

The report is always for one Mill (a Mill Master). Only the weighments of that mill's Transit Passes and the sent
records of that mill are used, so every row and every total belongs to the selected mill.
"""

from __future__ import annotations


def _int(value) -> int:
	try:
		return int(value or 0)
	except (TypeError, ValueError):
		return 0


def _qty(value) -> float:
	try:
		return round(float(value or 0), 3)
	except (TypeError, ValueError):
		return 0.0


def remaining_bags(debit: int, credit: int):
	"""Debit - Credit, shown only when there is Debit; never below 0. None (an empty cell) when nothing was sent."""
	if not debit or debit <= 0:
		return None
	return max(debit - credit, 0)


def is_completed_trip(wbm: dict, qc_bags: dict, wbms_with_grn: set) -> bool:
	qc = (wbm.get("quality_check") or "").strip()
	return bool(qc) and qc in qc_bags and wbm["name"] in wbms_with_grn


def wbms_of_mill(wbms, party_of, mill) -> list[dict]:
	"""The weighments whose Transit Pass belongs to this Mill Master.

	party_of: (operating unit, PPC) of each Pass Unique Key as master names. A pass whose mill could not be matched
	to a Mill Master cannot be attributed to a mill and is left out."""
	mill = (mill or "").strip()
	if not mill:
		return []
	return [
		w for w in wbms if (party_of.get((w.get("pass_unique_key") or "").strip()) or (None, None))[0] == mill
	]


def build_ledger_rows(
	wbms, qc_bags, wbms_with_grn, transit_passes, party_of=None, sent=None, names_for=None, mill_name=None
) -> list[dict]:
	"""wbms: WBM dicts (name, pass_unique_key, quality_check, net_weight).
	qc_bags: physical bag count by Quality Check name, for the Quality Checks that exist.
	wbms_with_grn: names of WBMs that have a GRN Note.
	transit_passes: PPAS Transit Pass dicts by Pass Unique Key (miller, ppc): the names shown.
	party_of: (operating unit, PPC) of each Pass Unique Key, as master names; either may be missing.
	sent: submitted Gunny Bags Sent to PPC dicts (operating_unit, ppc, bags_sent).
	names_for: (operating unit, PPC) -> (mill name, PPC name), for a row that exists only through a sent record.
	mill_name: when given (the full name of the selected Mill Master), it is the Mill Name of every row."""
	party_of = party_of or {}
	groups: dict[tuple[str, str], dict] = {}

	def group(group_key, mill_name, ppc_name):
		return groups.setdefault(
			group_key, {"mill": mill_name, "ppc": ppc_name, "qty": 0.0, "debit": 0, "credit": 0}
		)

	seen: set[str] = set()
	for wbm in sorted(wbms, key=lambda w: w["name"]):
		key = (wbm.get("pass_unique_key") or "").strip()
		if not key or wbm["name"] in seen:
			continue
		seen.add(wbm["name"])
		if not is_completed_trip(wbm, qc_bags, wbms_with_grn):
			continue
		tp = transit_passes.get(key) or {}
		unit, ppc = party_of.get(key) or (None, None)
		g = group(
			(unit or f"~{tp.get('miller') or ''}", ppc or f"~{tp.get('ppc') or ''}"),
			tp.get("miller") or "",
			tp.get("ppc") or "",
		)
		g["qty"] = _qty(g["qty"] + _qty(wbm.get("net_weight")))
		g["credit"] += _int(qc_bags.get((wbm.get("quality_check") or "").strip()))

	for record in sent or []:
		unit, ppc = record.get("operating_unit"), record.get("ppc")
		if not unit or not ppc:
			continue
		sent_mill, sent_ppc = names_for(unit, ppc) if names_for else (unit, ppc)
		group((unit, ppc), sent_mill, sent_ppc)["debit"] += _int(record.get("bags_sent"))

	rows = [
		{
			"mill_name": mill_name or g["mill"],
			"ppc_name": g["ppc"],
			"qty": g["qty"],
			"debit_bags": g["debit"],
			"credit_bags": g["credit"],
			"remaining_bags": remaining_bags(g["debit"], g["credit"]),
		}
		for g in groups.values()
	]
	return sorted(rows, key=lambda r: (r["mill_name"], r["ppc_name"]))
