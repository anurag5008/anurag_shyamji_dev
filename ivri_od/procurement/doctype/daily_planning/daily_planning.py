# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, today

# TODO: set False to limit plan date to today + 3 days again
ALLOW_ANY_PLAN_DATE = True


def _normalize_match_values(*values):
	return {str(value).strip().upper() for value in values if value and str(value).strip()}


def _compact_upper(value):
	"""Ignore spaces when matching PPAS Excel PPC text to PPC Master."""
	if value is None:
		return ""
	return "".join(str(value).strip().upper().split())


def _ppc_transit_match_values(ppc_master_name):
	"""
	Values to match `PPAS Transit Pass.ppc` (often imported as GAMBHARI(S1050406))
	against PPC Master (title is GAMBHARI (S1050406)).
	"""
	base = _master_match_values("PPC Master", ppc_master_name, ["code", "ppc_name", "title"])
	if not base:
		return set()

	compact = {_compact_upper(value) for value in base}
	row = frappe.db.get_value("PPC Master", ppc_master_name, ["code", "ppc_name"], as_dict=True) or {}
	code = (row.get("code") or "").strip().upper()
	ppc_label = (row.get("ppc_name") or "").strip()
	if code and ppc_label:
		compact.add(_compact_upper(f"{ppc_label}({code})"))
		compact.add(_compact_upper(f"{ppc_label} ({code})"))
	return {value for value in compact if value}


def _master_match_values(doctype, name, fields):
	if not name or not frappe.db.exists(doctype, name):
		return set()

	match_values = _normalize_match_values(name)
	row = frappe.db.get_value(doctype, name, fields, as_dict=True) or {}
	for fieldname in fields:
		match_values |= _normalize_match_values(row.get(fieldname))
	return match_values


def count_transit_pass_trucks(plan_date, ppc_name):
	"""
	Count PPAS Transit Pass rows for the plan:
	- transit_pass_date = plan_date
	- ppc matches PPC Master
	Each transit pass = one truck loaded.
	"""
	if not plan_date or not ppc_name:
		return 0

	ppc_values = sorted(_ppc_transit_match_values(ppc_name))
	if not ppc_values:
		return 0

	ppc_placeholders = ", ".join(["%s"] * len(ppc_values))
	params = [getdate(plan_date), *ppc_values]

	return cint(
		frappe.db.sql(
			f"""
			SELECT COUNT(*) AS cnt
			FROM `tabPPAS Transit Pass`
			WHERE transit_pass_date = %s
				AND REPLACE(UPPER(TRIM(IFNULL(ppc, ''))), ' ', '') IN ({ppc_placeholders})
			""",
			params,
		)[0][0]
	)


def compute_truck_totals(plan_date, ppc_name, trucks_sent):
	loaded = count_transit_pass_trucks(plan_date, ppc_name)
	sent = cint(trucks_sent)
	remaining = max(sent - loaded, 0)
	return {"trucks_loaded": loaded, "trucks_remaining": remaining}


@frappe.whitelist()
def get_truck_load_from_transit_pass(plan_date, ppc_name, trucks_sent=0):
	return compute_truck_totals(plan_date, ppc_name, trucks_sent)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_pacs_for_ppc(doctype, txt, searchfield, start, page_len, filters):
	filters = frappe.parse_json(filters) if filters else {}
	ppc_name = filters.get("ppc_name")
	conditions = ["(name LIKE %s OR code LIKE %s OR ppc_name LIKE %s)"]
	values = [f"%{txt}%", f"%{txt}%", f"%{txt}%"]

	if ppc_name:
		ppc_values = sorted(_master_match_values("PPC Master", ppc_name, ["code", "ppc_name", "title"]))
		if ppc_values:
			placeholders = ", ".join(["%s"] * len(ppc_values))
			conditions.append(f"(ppc_name IN ({placeholders}) OR name IN ({placeholders}))")
			values.extend(ppc_values)
			values.extend(ppc_values)

	return frappe.db.sql(
		f"""
		SELECT name
		FROM `tabSociety Master`
		WHERE {" AND ".join(conditions)}
		ORDER BY name
		LIMIT %s, %s
		""",
		(*values, start, page_len),
	)


class DailyPlanning(Document):
	def validate(self):
		self.validate_plan_date()
		self.trucks_sent = cint(self.trucks_sent)
		self.average_truck_capacity = flt(self.average_truck_capacity) or 250
		self.update_trucks_from_transit_pass()
		self.calculate_estimated_paddy()

	def validate_plan_date(self):
		if ALLOW_ANY_PLAN_DATE or not self.plan_date:
			return

		plan_date = getdate(self.plan_date)
		min_date = getdate(today())
		max_date = getdate(add_days(today(), 3))

		if plan_date < min_date or plan_date > max_date:
			frappe.throw(
				f"Daily Planning is allowed only for today and the next 3 days "
				f"({min_date.strftime('%d-%m-%Y')} to {max_date.strftime('%d-%m-%Y')})"
			)

	def update_trucks_from_transit_pass(self):
		totals = compute_truck_totals(self.plan_date, self.ppc_name, self.trucks_sent)
		self.trucks_loaded = totals["trucks_loaded"]
		self.trucks_remaining = totals["trucks_remaining"]

	def calculate_estimated_paddy(self):
		self.estimated_paddy = flt(self.trucks_sent) * flt(self.average_truck_capacity)
