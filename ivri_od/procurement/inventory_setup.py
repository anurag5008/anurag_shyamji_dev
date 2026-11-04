# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

"""Configuration plan for the inventory structure: legal Companies, physical locations, unit-to-Company
mapping, warehouses and Items.

Warehouses: exactly one SHARED warehouse per physical location (nine), under the location's legal Company. Raw and
Boiled units share it; the unit that owns stock is kept on the batch, the Stock Entry and the Bag Ledger. The older
per-unit warehouses (one per unit and location) are removed in a separate reviewed step, delete_legacy_warehouses()
(or only disabled with retire_legacy_warehouses()), and only when a shared warehouse exists for their place and
no stock, posting, bag entry or document refers to them.

Two steps, kept apart on purpose:
1. build_plan(): READS only. Lists what would be created or updated, what already exists and what is
   blocked or still undecided, with a plan_hash over its content. Safe to run any time.
2. apply_plan(plan_hash): runs only a plan whose hash was reviewed. It never renames, merges, deletes or
   edits an existing Company or Warehouse, never enables stock posting, never sets a rate.

Idempotent: a step whose target already exists is "exists" and is skipped, so a second run does nothing.
Nothing is guessed: an undecided item (warehouse pairs, Items) is reported as pending, not invented.
"""

import hashlib
import json
import os

import frappe
from frappe import _
from frappe.utils import cint

from ivri_od.procurement.inventory_foundation import (
	APPROVED_LOCATIONS,
	APPROVED_UNITS,
	LEGAL_COMPANIES,
	approved_company_for_unit,
)

CREATE, UPDATE, EXISTS, BLOCKED, PENDING = "create", "update", "exists", "blocked", "pending_decision"
RETIRE = "retire"  # planned, but never run by apply_plan()
RETIRE_CONFIRMATION = "disable legacy warehouses"
DELETE_CONFIRMATION = "delete legacy warehouses"
ACTIONABLE = (CREATE, UPDATE)
APPROVED_FILE = os.path.join(os.path.dirname(__file__), "inventory_setup_approved.json")
# Company settings copied from the existing Companies, never chosen here.
TEMPLATE_FIELDS = (
	"default_currency", "country", "valuation_method", "chart_of_accounts",
	"create_chart_of_accounts_based_on", "enable_perpetual_inventory",
)
ITEM_ROLES = ("paddy", "raw_rice", "boiled_rice", "by_product")
SETTING_FIELD = {"paddy": "government_paddy_item", "raw_rice": "raw_rice_item", "boiled_rice": "boiled_rice_item"}


# ---- reading ----


def load_approved() -> dict:
	with open(APPROVED_FILE) as handle:
		data = json.load(handle)
	return {"warehouses": data.get("warehouses") or [], "items": data.get("items") or []}


def read_snapshot() -> dict:
	"""Everything the plan depends on, read once. No writes."""
	companies = {
		c.name: c
		for c in frappe.get_all(
			"Company", fields=["name", "abbr", *TEMPLATE_FIELDS], limit_page_length=0
		)
	}
	settings = frappe.get_cached_doc("Stock Posting Settings")
	return {
		"companies": companies,
		"locations": {
			l.name: l.company
			for l in frappe.get_all("Physical Location", fields=["name", "company"], limit_page_length=0)
		},
		"mills": {
			m.name: m
			for m in frappe.get_all("Mill Master", fields=["name", "type", "accounting_company"], limit_page_length=0)
		},
		"warehouses": frappe.get_all(
			"Warehouse",
			fields=["name", "company", "operating_unit", "physical_location", "disabled", "is_group"],
			limit_page_length=0,
		),
		"items": {i.name: i for i in frappe.get_all("Item", fields=["name", "item_group"], limit_page_length=0)},
		"item_groups": set(frappe.get_all("Item Group", pluck="name")),
		"uoms": set(frappe.get_all("UOM", pluck="name")),
		"settings": {
			"enabled": cint(settings.enabled),
			**{field: settings.get(field) or "" for field in SETTING_FIELD.values()},
			"by_products": [row.item_code for row in settings.by_product_items],
		},
	}


# ---- planning (pure) ----


def _step(step_id, kind, name, action, values=None, depends_on=(), note=""):
	return {
		"id": step_id, "kind": kind, "name": name, "action": action,
		"values": values or {}, "depends_on": list(depends_on), "note": note,
	}


def company_template(snapshot) -> tuple[dict | None, str]:
	"""Settings of the existing Companies, if they all agree. Otherwise None and the reason."""
	rows = [c for c in snapshot["companies"].values()]
	if not rows:
		return None, "No existing Company to copy settings from."
	template = {f: rows[0].get(f) for f in TEMPLATE_FIELDS}
	for row in rows[1:]:
		differing = [f for f in TEMPLATE_FIELDS if row.get(f) != template[f]]
		if differing:
			return None, "Existing Companies disagree on: " + ", ".join(differing)
	return template, ""


def plan_from_snapshot(snapshot: dict, approved: dict) -> dict:
	steps = []
	template, template_issue = company_template(snapshot)
	companies = snapshot["companies"]
	by_abbr = {c.abbr: c.name for c in companies.values()}

	# 1. legal Companies
	for abbr, name in LEGAL_COMPANIES.items():
		step_id = f"company:{abbr}"
		if name in companies:
			if companies[name].abbr != abbr:
				steps.append(_step(step_id, "Company", name, BLOCKED, note=f"exists with abbreviation {companies[name].abbr}, approved is {abbr}"))
			else:
				steps.append(_step(step_id, "Company", name, EXISTS))
		elif abbr in by_abbr:
			steps.append(_step(step_id, "Company", name, BLOCKED, note=f"abbreviation {abbr} is already used by {by_abbr[abbr]}"))
		elif template is None:
			steps.append(_step(step_id, "Company", name, BLOCKED, note=template_issue))
		else:
			steps.append(_step(step_id, "Company", name, CREATE, {"company_name": name, "abbr": abbr, **template}))

	def company_ready(abbr):
		step = next(s for s in steps if s["id"] == f"company:{abbr}")
		return step["action"] in (CREATE, EXISTS)

	# 2. nine physical locations
	for abbr, names in APPROVED_LOCATIONS.items():
		for short in names:
			name = f"{abbr} {short}"
			step_id = f"location:{name}"
			expected = LEGAL_COMPANIES[abbr]
			if name in snapshot["locations"]:
				if snapshot["locations"][name] != expected:
					steps.append(_step(step_id, "Physical Location", name, BLOCKED, note=f"belongs to {snapshot['locations'][name]}, approved {expected}"))
				else:
					steps.append(_step(step_id, "Physical Location", name, EXISTS))
			elif not company_ready(abbr):
				steps.append(_step(step_id, "Physical Location", name, BLOCKED, note=f"Company {expected} is not available"))
			else:
				steps.append(_step(step_id, "Physical Location", name, CREATE, {"location_name": name, "company": expected}, [f"company:{abbr}"]))

	# 3. operating unit -> legal Company (the only change to an existing Mill Master: an empty field)
	for code, spec in APPROVED_UNITS.items():
		step_id = f"unit:{code}"
		expected = approved_company_for_unit(code)
		mill = snapshot["mills"].get(code)
		if not mill:
			steps.append(_step(step_id, "Mill Master", code, BLOCKED, note="Mill Master record is missing"))
		elif mill.type != spec["type"]:
			steps.append(_step(step_id, "Mill Master", code, BLOCKED, note=f"type is {mill.type}, approved {spec['type']}"))
		elif (mill.accounting_company or "") == expected:
			steps.append(_step(step_id, "Mill Master", code, EXISTS))
		elif mill.accounting_company:
			steps.append(_step(step_id, "Mill Master", code, BLOCKED, note=f"accounting_company is already {mill.accounting_company}"))
		elif not company_ready(spec["abbr"]):
			steps.append(_step(step_id, "Mill Master", code, BLOCKED, note=f"Company {expected} is not available"))
		else:
			steps.append(_step(step_id, "Mill Master", code, UPDATE, {"accounting_company": expected}, [f"company:{spec['abbr']}"]))

	# 4. warehouses. An approved entry with only a "location" is the SHARED physical warehouse of that location under
	#    its legal Company (the standard). An entry that also names a "unit" is the older per-unit warehouse.
	known_locations = {f"{a} {n}" for a, ns in APPROVED_LOCATIONS.items() for n in ns}
	live_pairs = {(w.operating_unit, w.physical_location): w.name for w in snapshot["warehouses"] if w.operating_unit and not w.disabled and not w.is_group}
	live_shared = {
		(w.company, w.physical_location): w.name
		for w in snapshot["warehouses"]
		if not w.operating_unit and w.physical_location and not w.disabled and not w.is_group
	}
	live = live_pairs
	seen = set()
	shared_wanted = False
	for entry in approved["warehouses"]:
		unit, location = entry.get("unit"), entry.get("location")
		if not unit:
			shared_wanted = True
			step_id = f"warehouse:shared|{location}"
			abbr = (location or "").split(" ", 1)[0]
			if (None, location) in seen:
				steps.append(_step(step_id + "#dup", "Warehouse", f"shared|{location}", BLOCKED, note="listed twice in the approved file"))
				continue
			seen.add((None, location))
			if location not in known_locations or abbr not in LEGAL_COMPANIES:
				steps.append(_step(step_id, "Warehouse", f"shared|{location}", BLOCKED, note="the location is not one of the approved ones"))
				continue
			company = LEGAL_COMPANIES[abbr]
			if (company, location) in live_shared:
				steps.append(_step(step_id, "Warehouse", live_shared[(company, location)], EXISTS))
				continue
			short = location[len(abbr) + 1:]
			steps.append(_step(
				step_id, "Warehouse", f"{short} - {abbr}", CREATE,
				{"warehouse_name": short, "company": company, "parent_warehouse": f"All Warehouses - {abbr}", "physical_location": location},
				[f"company:{abbr}", f"location:{location}"],
			))
			continue
		step_id = f"warehouse:{unit}|{location}"
		spec = APPROVED_UNITS.get(unit)
		if (unit, location) in seen:
			steps.append(_step(step_id + "#dup", "Warehouse", f"{unit}|{location}", BLOCKED, note="listed twice in the approved file"))
			continue
		seen.add((unit, location))
		if not spec or location not in known_locations:
			steps.append(_step(step_id, "Warehouse", f"{unit}|{location}", BLOCKED, note="unit or location is not one of the approved ones"))
			continue
		if not location.startswith(spec["abbr"] + " "):
			steps.append(_step(step_id, "Warehouse", f"{unit}|{location}", BLOCKED, note="location belongs to another legal Company; cross-Company sharing needs a separate approval"))
			continue
		if (unit, location) in live:
			steps.append(_step(step_id, "Warehouse", live[(unit, location)], EXISTS))
			continue
		short = location[len(spec["abbr"]) + 1:]
		warehouse_name = f"{short} {spec['type'].title()}"
		company = LEGAL_COMPANIES[spec["abbr"]]
		steps.append(_step(
			step_id, "Warehouse", f"{warehouse_name} - {spec['abbr']}", CREATE,
			{"warehouse_name": warehouse_name, "company": company, "parent_warehouse": f"All Warehouses - {spec['abbr']}",
			 "operating_unit": unit, "physical_location": location},
			[f"company:{spec['abbr']}", f"location:{location}", f"unit:{unit}"],
		))
	if shared_wanted:
		# the older per-unit warehouses: listed for retirement, never run by apply_plan
		for w in sorted(snapshot["warehouses"], key=lambda w: w.name):
			if w.operating_unit and not w.disabled and not w.is_group:
				steps.append(_step(
					f"legacy:{w.name}", "Warehouse", w.name, RETIRE,
					{"physical_location": w.physical_location, "operating_unit": w.operating_unit},
					note="older per-unit warehouse: remove with delete_legacy_warehouses() after review (only if nothing refers to it)",
				))
	if not approved["warehouses"]:
		candidates = [f"{code} @ {a} {n}" for code, s in APPROVED_UNITS.items() for a in [s["abbr"]] for n in APPROVED_LOCATIONS[a]]
		steps.append(_step(
			"warehouses:pending", "Warehouse", "(owner, location) pairs", PENDING,
			{"candidates": candidates},
			note="Which physical locations really hold stock has not been approved. Fill 'warehouses' in inventory_setup_approved.json.",
		))

	# 5. Items and their roles in Stock Posting Settings
	items = approved["items"]
	if not items:
		steps.append(_step("items:pending", "Item", "paddy, raw rice, boiled rice, by-products", PENDING,
			note="Item codes, names and groups have not been approved. Fill 'items' in inventory_setup_approved.json."))
	for entry in items:
		role, code = entry.get("role"), (entry.get("item_code") or "").strip()
		step_id = f"item:{code}"
		if role not in ITEM_ROLES or not code or not (entry.get("item_name") or "").strip():
			steps.append(_step(step_id, "Item", code or "?", BLOCKED, note="needs role, item_code and item_name"))
		elif entry.get("item_group") not in snapshot["item_groups"]:
			steps.append(_step(step_id, "Item", code, BLOCKED, note=f"Item Group {entry.get('item_group')} does not exist"))
		elif "Quintal" not in snapshot["uoms"]:
			steps.append(_step(step_id, "Item", code, BLOCKED, note="UOM Quintal does not exist"))
		elif code in snapshot["items"]:
			steps.append(_step(step_id, "Item", code, EXISTS, note="existing Item is not changed"))
		else:
			steps.append(_step(step_id, "Item", code, CREATE, {
				"item_code": code, "item_name": entry["item_name"].strip(), "item_group": entry["item_group"],
				"stock_uom": "Quintal", "is_stock_item": 1, "has_batch_no": 1, "role": role,
			}))
	roles_in_file = [e.get("role") for e in items]
	for role in ("paddy", "raw_rice", "boiled_rice"):
		if items and roles_in_file.count(role) != 1:
			steps.append(_step(f"items:role:{role}", "Item", role, BLOCKED, note=f"exactly one {role} Item is required, found {roles_in_file.count(role)}"))
	for entry in items:
		role, code = entry.get("role"), (entry.get("item_code") or "").strip()
		if role in SETTING_FIELD and code and snapshot["settings"][SETTING_FIELD[role]] in ("", code):
			already = snapshot["settings"][SETTING_FIELD[role]] == code
			steps.append(_step(f"settings:{role}", "Stock Posting Settings", SETTING_FIELD[role], EXISTS if already else UPDATE,
				{SETTING_FIELD[role]: code}, [] if already else [f"item:{code}"]))
		elif role in SETTING_FIELD and code:
			steps.append(_step(f"settings:{role}", "Stock Posting Settings", SETTING_FIELD[role], BLOCKED, note="already set to a different Item"))
		elif role == "by_product" and code:
			already = code in snapshot["settings"]["by_products"]
			steps.append(_step(f"settings:by_product:{code}", "Stock Posting Settings", "by_product_items", EXISTS if already else UPDATE,
				{"by_product_item": code}, [] if already else [f"item:{code}"]))

	core = [{k: s[k] for k in ("id", "kind", "name", "action", "values", "depends_on")} for s in steps]
	plan_hash = hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()
	counts = {}
	for s in steps:
		counts[s["action"]] = counts.get(s["action"], 0) + 1
	return {
		"plan_hash": plan_hash,
		"posting_enabled": snapshot["settings"]["enabled"],
		"counts": counts,
		"steps": steps,
		"blocked": [s for s in steps if s["action"] == BLOCKED],
		"pending": [s for s in steps if s["action"] == PENDING],
	}


def build_plan() -> dict:
	"""Read-only plan from the live data. Safe to run any time."""
	return plan_from_snapshot(read_snapshot(), load_approved())


def print_plan() -> str:
	"""For `bench --site shyamji execute ivri_od.procurement.inventory_setup.print_plan`."""
	return format_plan(build_plan())


def format_plan(plan: dict) -> str:
	lines = [f"plan_hash: {plan['plan_hash']}", f"stock posting enabled: {plan['posting_enabled']}", f"counts: {plan['counts']}", ""]
	for s in plan["steps"]:
		extra = s["note"] or (json.dumps(s["values"], default=str) if s["action"] in ACTIONABLE else "")
		lines.append(f"[{s['action']:>16}] {s['kind']}: {s['name']}  {extra}")
	return "\n".join(lines)


# ---- the older per-unit warehouses ----


def legacy_safety(warehouse, references: dict, has_shared_replacement: bool) -> list[str]:
	"""Reasons a per-unit warehouse must not be disabled yet. Empty means it is safe to disable. Pure."""
	reasons = []
	if not has_shared_replacement:
		reasons.append("its physical location has no shared warehouse yet")
	for name, count in references.items():
		if count:
			reasons.append(f"{count} {name.replace('_', ' ')}")
	return reasons


@frappe.whitelist()
def legacy_warehouse_report() -> list[dict]:
	"""READ ONLY. Every per-unit warehouse, what refers to it and whether it could be disabled. Changes nothing."""
	frappe.only_for(("System Manager", "Stock Manager"))
	shared = {
		(w.company, w.physical_location)
		for w in frappe.get_all(
			"Warehouse",
			filters={"operating_unit": ["is", "not set"], "physical_location": ["is", "set"], "is_group": 0, "disabled": 0},
			fields=["company", "physical_location"],
			limit_page_length=0,
		)
	}
	report = []
	for w in frappe.get_all(
		"Warehouse",
		filters={"operating_unit": ["is", "set"], "is_group": 0},
		fields=["name", "company", "operating_unit", "physical_location", "disabled"],
		order_by="name",
		limit_page_length=0,
	):
		refs = {
			"stock_ledger_entries": frappe.db.count("Stock Ledger Entry", {"warehouse": w.name}),
			"bins_with_stock": frappe.db.count("Bin", {"warehouse": w.name, "actual_qty": ["!=", 0]}),
			"stock_posting_logs": frappe.db.count("Stock Posting Log", {"warehouse": w.name}),
			"bag_ledger_entries": frappe.db.count("Bag Ledger Entry", {"warehouse": w.name}),
			"stock_entry_rows": frappe.db.count("Stock Entry Detail", {"s_warehouse": w.name})
			+ frappe.db.count("Stock Entry Detail", {"t_warehouse": w.name}),
			"quality_checks_naming_it": frappe.db.count("Quality Check", {"unloading_point": w.name}),
			"grn_notes_naming_it": frappe.db.count("GRN Note", {"unloading_point": w.name}),
		}
		reasons = legacy_safety(w, refs, (w.company, w.physical_location) in shared)
		report.append({**w, **refs, "blocked_by": reasons, "safe_to_disable": not reasons and not cint(w.disabled)})
	return report


@frappe.whitelist()
def retire_legacy_warehouses(confirmation: str) -> dict:
	"""Disable (never delete) the per-unit warehouses that are safe to disable: a shared warehouse exists for their
	location and no stock, posting, bag entry or document refers to them. Needs the exact confirmation phrase."""
	frappe.only_for("System Manager")
	if cint(frappe.get_cached_doc("Stock Posting Settings").enabled):
		frappe.throw(_("Stock posting is enabled. Disable it before changing the configuration."))
	if (confirmation or "").strip() != RETIRE_CONFIRMATION:
		frappe.throw(_("Type the confirmation phrase exactly: {0}").format(RETIRE_CONFIRMATION), title=_("Not Confirmed"))
	disabled, kept = [], []
	for row in legacy_warehouse_report():
		if row["safe_to_disable"]:
			frappe.db.set_value("Warehouse", row["name"], "disabled", 1)
			disabled.append(row["name"])
		elif not cint(row["disabled"]):
			kept.append({"warehouse": row["name"], "blocked_by": row["blocked_by"]})
	return {"disabled": disabled, "kept": kept}


@frappe.whitelist()
def delete_legacy_warehouses(confirmation: str) -> dict:
	"""Delete the per-unit warehouses that are safe to remove: a shared warehouse exists for their place and no stock,
	posting, bag entry or document refers to them. A warehouse that anything refers to is kept and reported.
	Needs the exact confirmation phrase; Frappe's own link check still applies to every delete."""
	frappe.only_for("System Manager")
	if cint(frappe.get_cached_doc("Stock Posting Settings").enabled):
		frappe.throw(_("Stock posting is enabled. Disable it before changing the configuration."))
	if (confirmation or "").strip() != DELETE_CONFIRMATION:
		frappe.throw(_("Type the confirmation phrase exactly: {0}").format(DELETE_CONFIRMATION), title=_("Not Confirmed"))
	deleted, kept = [], []
	for row in legacy_warehouse_report():
		if row["blocked_by"]:
			kept.append({"warehouse": row["name"], "blocked_by": row["blocked_by"]})
			continue
		frappe.delete_doc("Warehouse", row["name"])
		deleted.append(row["name"])
	return {"deleted": deleted, "kept": kept}


# ---- applying ----


def _run_step(step: dict) -> str:
	kind, values = step["kind"], step["values"]
	if kind == "Company":
		frappe.get_doc({"doctype": "Company", **values}).insert()
		return values["company_name"]
	if kind == "Physical Location":
		frappe.get_doc({"doctype": "Physical Location", **values}).insert()
		return values["location_name"]
	if kind == "Mill Master":
		doc = frappe.get_doc("Mill Master", step["name"])
		if doc.accounting_company:  # only an empty field may be filled
			frappe.throw(_("Mill Master {0} already has an Accounting Company.").format(step["name"]))
		doc.accounting_company = values["accounting_company"]
		doc.save()
		return step["name"]
	if kind == "Warehouse":
		doc = frappe.get_doc({"doctype": "Warehouse", **values})
		doc.insert()
		return doc.name
	if kind == "Item":
		doc = frappe.get_doc({"doctype": "Item", **{k: v for k, v in values.items() if k != "role"}})
		doc.insert()
		return doc.name
	if kind == "Stock Posting Settings":
		settings = frappe.get_doc("Stock Posting Settings")
		if "by_product_item" in values:
			settings.append("by_product_items", {"item_code": values["by_product_item"]})
		else:
			for field, value in values.items():
				if settings.get(field):
					frappe.throw(_("{0} is already set.").format(field))
				settings.set(field, value)
		settings.save()  # 'enabled' is never touched here
		return "Stock Posting Settings"
	frappe.throw(_("Unknown step kind {0}.").format(kind))


@frappe.whitelist()
def apply_plan(plan_hash: str) -> dict:
	"""Run the reviewed plan. Stops at the first failure; a rerun continues where it stopped."""
	frappe.only_for("System Manager")
	plan = build_plan()
	if plan["posting_enabled"]:
		frappe.throw(_("Stock posting is enabled. Disable it before changing the configuration."))
	if (plan_hash or "").strip() != plan["plan_hash"]:
		frappe.throw(_("The plan has changed since it was reviewed. Run print_plan again and review it."), title=_("Plan Changed"))
	if plan["blocked"]:
		frappe.throw(
			_("The plan has blocked steps. Resolve them first:") + "<br>" + "<br>".join(f"{s['id']}: {s['note']}" for s in plan["blocked"]),
			title=_("Blocked Plan"),
		)
	done, skipped = [], []
	finished = {s["id"] for s in plan["steps"] if s["action"] == EXISTS}
	for step in plan["steps"]:
		if step["action"] not in ACTIONABLE:
			continue
		if any(dep not in finished for dep in step["depends_on"]):
			skipped.append(step["id"])
			continue
		_run_step(step)
		finished.add(step["id"])
		done.append(step["id"])
	return {"applied": done, "skipped_missing_dependency": skipped}
