# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt, get_time, getdate, nowdate

from ivri_od.procurement.mill_gate import get_qc_sl_no, normalize_vehicle_no


def _ppc_display_name(party_link: str | None) -> str:
	"""Readable PPC name from Quality Check party_name (PPC or Society Master link)."""
	link = (party_link or "").strip()
	if not link:
		return ""
	if frappe.db.exists("PPC Master", link):
		return (frappe.db.get_value("PPC Master", link, "ppc_name") or link).strip()
	if frappe.db.exists("Society Master", link):
		return (frappe.db.get_value("Society Master", link, "ppc_name") or link).strip()
	return link


class GRNNote(Document):
	def autoname(self):
		"""GRN-2026-00001 — year from receipt date, sequence resets per year."""
		year = getdate(self.receipt_date or nowdate()).year
		self.name = make_autoname(f"GRN-{year}-.#####", doc=self)

	def before_insert(self):
		self._assign_grn_no()

	def validate(self):
		self._ensure_grn_no()
		self._normalize_fields()
		self._validate_pass_unique_key()
		self._sync_from_transit_pass()
		self._sync_entry_details_from_pass()
		self._validate_and_sync_rst()
		self._sync_ppc_name_from_quality_check()

	def _sync_ppc_name_from_quality_check(self):
		qc_name = (self.quality_check or "").strip()
		if not qc_name or not frappe.db.exists("Quality Check", qc_name):
			self.ppc_name = ""
			self.qc_bag_details = []
			return
		ppc_link = (frappe.db.get_value("Quality Check", qc_name, "party_name") or "").strip()
		self.ppc_name = _ppc_display_name(ppc_link)

	def _assign_grn_no(self):
		"""Sequential GRN No from naming series (same value as document name)."""
		if not (self.grn_no or "").strip() and (self.name or "").strip():
			self.grn_no = self.name.strip()

	def _ensure_grn_no(self):
		if self.is_new():
			return
		if not (self.grn_no or "").strip() and (self.name or "").strip():
			self.grn_no = self.name.strip()
		elif (self.grn_no or "").strip() != (self.name or "").strip():
			self.grn_no = self.name.strip()

	def _normalize_fields(self):
		self.pass_unique_key = (self.pass_unique_key or "").strip()
		self.rst_no = (self.rst_no or "").strip()
		if self.paddy_variety:
			self.paddy_variety = self.paddy_variety.strip()

	def _validate_pass_unique_key(self):
		if not self.pass_unique_key:
			frappe.throw(_("Select Pass Unique Key from PPAS Transit Pass."))
		if not frappe.db.exists("PPAS Transit Pass", {"pass_unique_key": self.pass_unique_key}):
			frappe.throw(
				_("No PPAS Transit Pass found for Pass Unique Key {0}.").format(
					frappe.bold(self.pass_unique_key)
				)
			)

	def _sync_entry_details_from_pass(self):
		key = (self.pass_unique_key or "").strip()
		self.entry_details = []
		if not key:
			return
		for row in _entry_rows_for_pass(key):
			child = self.append("entry_details", {})
			child.entry = row.get("entry")
			child.entry_date = row.get("entry_date")
			child.entry_time = row.get("entry_time")
			child.agent_name = row.get("agent_name") or ""
			child.pacs_name = row.get("pacs_name") or ""
			child.entry_quantity = flt(row.get("entry_quantity"))
			child.entry_price_per_quintal = flt(row.get("entry_price_per_quintal"))
			child.total_amount = flt(row.get("total_amount"))

	def _sync_from_transit_pass(self):
		tp = frappe.db.get_value(
			"PPAS Transit Pass",
			{"pass_unique_key": self.pass_unique_key},
			[
				"season",
				"transit_pass_no",
				"transit_pass_date",
				"quantity",
				"pacs",
				"ppc",
			],
			as_dict=True,
		)
		if not tp:
			return

		self.cmr_season = (tp.season or "").strip()
		self.transit_pass_no = tp.transit_pass_no
		self.transit_pass_date = tp.transit_pass_date
		self.tp_quantity = flt(tp.quantity)
		self.pacs = (tp.pacs or "").strip()
		self.ppc = (tp.ppc or "").strip()

	def _validate_and_sync_rst(self):
		rst_no = (self.rst_no or "").strip()
		if not rst_no:
			frappe.throw(_("Enter RST No from Weigh Bridge Measurement."))

		wbm_name = _resolve_wbm_for_rst(rst_no, self.pass_unique_key)
		if not wbm_name:
			frappe.throw(
				_("No Weigh Bridge Measurement found for RST No {0}.").format(frappe.bold(rst_no))
			)

		self.weigh_bridge_measurement = wbm_name
		self._apply_weigh_bridge(wbm_name)
		qc_name = (self.quality_check or "").strip()
		if qc_name:
			self._apply_quality_check(qc_name)
		self._apply_gate_entry((self.gate_entry or "").strip())

	def _apply_weigh_bridge(self, wbm_name: str):
		wbm = frappe.db.get_value(
			"Weigh Bridge Measurement",
			wbm_name,
			[
				"pass_unique_key",
				"quality_test",
				"load_weight",
				"gross_weight",
				"tare_weight",
				"net_weight",
				"gunny_type",
				"gunny_weight",
				"gate_entry",
				"quality_check",
				"slno_of_qc",
				"no_of_bags",
				"actual_truck_no",
				"truck_no_in_tp",
				"vehicle_no",
				"is_farmer_or_agent",
			],
			as_dict=True,
		)
		if not wbm:
			return
		if wbm.quality_test not in ("Accepted", "Partially Accepted"):
			frappe.throw(
				_("GRN Note can be created only when Quality Test is Accepted or Partially Accepted.")
			)
		if not flt(wbm.tare_weight):
			frappe.throw(_("GRN Note can be created only when tare weight is greater than zero."))

		if (wbm.pass_unique_key or "").strip() != self.pass_unique_key:
			frappe.throw(
				_(
					"RST No {0} belongs to Pass Unique Key {1}, not {2}."
				).format(
					frappe.bold(self.rst_no),
					frappe.bold(wbm.pass_unique_key),
					frappe.bold(self.pass_unique_key),
				)
			)

		self.gross_vehicle_weight = flt(wbm.load_weight)
		self.gross_weight = flt(wbm.gross_weight)
		self.tare_weight = flt(wbm.tare_weight)
		self.net_weight = flt(wbm.net_weight)
		self.gunny_type = wbm.gunny_type or ""
		self.gunny_weight = flt(wbm.gunny_weight)
		self.gate_entry = (wbm.gate_entry or "").strip()
		self.quality_check = (wbm.quality_check or "").strip()
		self.qc_sample_no = cint(wbm.slno_of_qc) or get_qc_sl_no(self.quality_check)
		if cint(wbm.no_of_bags):
			self.no_of_bags = cint(wbm.no_of_bags)

		if cint(wbm.is_farmer_or_agent):
			vehicle = (wbm.vehicle_no or "").strip()
		else:
			vehicle = (wbm.actual_truck_no or wbm.truck_no_in_tp or "").strip()
		self.vehicle_no = normalize_vehicle_no(vehicle)

	def _apply_quality_check(self, qc_name: str):
		if not frappe.db.exists("Quality Check", qc_name):
			return

		qc = frappe.db.get_value(
			"Quality Check",
			qc_name,
			[
				"name",
				"moisture",
				"dust",
				"staff_name",
				"unloading_point",
				"party_name",
				"paddy_type",
				"paddy_quality",
				"qc_decision",
				"paddy_received_in_pkt",
				"paddy_returned",
				"driver_name",
				"gate_entry",
			],
			as_dict=True,
		)
		if not qc:
			return

		self.moisture = flt(qc.moisture)
		self.dust = flt(qc.dust)
		self.unloader_name = (qc.staff_name or "").strip()
		self.unloading_point = (qc.unloading_point or "").strip()
		self.ppc_name = _ppc_display_name(qc.party_name)
		self.party_name = ""
		self.society_name = ""
		self.paddy_type = (qc.paddy_type or "").strip()
		self.paddy_quality = (qc.paddy_quality or "").strip()
		self.qc_decision = (qc.qc_decision or "").strip()
		self.paddy_received_in_pkt = cint(qc.paddy_received_in_pkt)
		self.paddy_returned = cint(qc.paddy_returned)
		if not self.no_of_bags:
			bags = _qc_bag_count(qc_name)
			if bags:
				self.no_of_bags = bags
			elif cint(qc.paddy_received_in_pkt):
				self.no_of_bags = cint(qc.paddy_received_in_pkt)

		if not (self.gate_entry or "").strip() and (qc.gate_entry or "").strip():
			self.gate_entry = qc.gate_entry.strip()
		if not (self.driver_name or "").strip() and (qc.driver_name or "").strip():
			self.driver_name = qc.driver_name.strip()

		self._apply_qc_bag_details(qc_name)

	def _apply_qc_bag_details(self, qc_name: str):
		self.qc_bag_details = []
		for row in _qc_bag_rows(qc_name):
			child = self.append("qc_bag_details", {})
			child.jute_pkt_no = cint(row.get("jute_pkt_no"))
			child.no_of_plastic_bag = cint(row.get("no_of_plastic_bag"))

	def _apply_gate_entry(self, gate_entry: str):
		if not gate_entry or not frappe.db.exists("Gate Entry", gate_entry):
			return

		ge = frappe.db.get_value(
			"Gate Entry",
			gate_entry,
			["entry_date", "entry_time", "driver_name", "vehicle_no", "in_out"],
			as_dict=True,
		)
		if not ge:
			return

		gate_in = gate_entry
		if ge.in_out == "Out":
			linked = frappe.db.get_value("Gate Entry", gate_entry, "gate_entry_in")
			if linked:
				gate_in = linked

		gate_in_row = frappe.db.get_value(
			"Gate Entry",
			gate_in,
			["entry_date", "entry_time", "driver_name", "vehicle_no"],
			as_dict=True,
		)
		if gate_in_row:
			self.arrival_date = gate_in_row.entry_date
			self.arrival_time = gate_in_row.entry_time
			if not (self.driver_name or "").strip():
				self.driver_name = (gate_in_row.driver_name or "").strip()
			if not (self.vehicle_no or "").strip():
				self.vehicle_no = normalize_vehicle_no(gate_in_row.vehicle_no)

		exit_datetime = frappe.db.get_value(
			"Gate Exit", {"gate_entry_in": gate_in}, "exit_datetime"
		)
		if exit_datetime:
			self.gate_out_time = get_time(exit_datetime)
		else:
			out_time = frappe.db.get_value(
				"Gate Entry", {"in_out": "Out", "gate_entry_in": gate_in}, "entry_time"
			)
			self.gate_out_time = out_time


def _resolve_wbm_for_rst(rst_no: str, pass_unique_key: str | None = None) -> str | None:
	rst_no = (rst_no or "").strip()
	if not rst_no:
		return None

	filters: dict = {"rst_no": rst_no}
	if (pass_unique_key or "").strip():
		filters["pass_unique_key"] = pass_unique_key.strip()

	names = frappe.get_all(
		"Weigh Bridge Measurement",
		filters=filters,
		pluck="name",
		order_by="modified desc",
		limit=1,
	)
	return names[0] if names else None


def _qc_bag_rows(qc_name: str) -> list[dict]:
	qc_name = (qc_name or "").strip()
	if not qc_name:
		return []
	return frappe.get_all(
		"Quality Check Bag Detail",
		filters={
			"parent": qc_name,
			"parenttype": "Quality Check",
			"parentfield": "type_of_pkt",
		},
		fields=["jute_pkt_no", "no_of_plastic_bag"],
		order_by="idx asc",
	)


def _qc_bag_count(qc_name: str) -> int:
	lines = frappe.get_all(
		"Quality Check Bag Detail",
		filters={
			"parent": qc_name,
			"parenttype": "Quality Check",
			"parentfield": "type_of_pkt",
		},
		fields=["jute_pkt_no", "no_of_plastic_bag", "jute_bags", "plastic_bags"],
	)
	total = 0
	for line in lines:
		jute = cint(line.jute_pkt_no) or cint(line.jute_bags)
		plastic = cint(line.no_of_plastic_bag) or cint(line.plastic_bags)
		total += jute + plastic
	return total


def _entry_rows_for_pass(pass_unique_key: str) -> list[dict]:
	key = (pass_unique_key or "").strip()
	if not key:
		return []
	rows = frappe.get_all(
		"Entry",
		filters={"pass_unique_key": key},
		fields=[
			"name",
			"entry_date",
			"entry_time",
			"agent_name",
			"pacs_name",
			"entry_quantity",
			"entry_price_per_quintal",
			"total_amount",
		],
		order_by="entry_date desc, entry_time desc, creation desc",
	)
	out = []
	for row in rows:
		out.append(
			{
				"entry": row.name,
				"entry_date": row.entry_date,
				"entry_time": row.entry_time,
				"agent_name": (row.agent_name or "").strip(),
				"pacs_name": (row.pacs_name or "").strip(),
				"entry_quantity": flt(row.entry_quantity),
				"entry_price_per_quintal": flt(row.entry_price_per_quintal),
				"total_amount": flt(row.total_amount),
			}
		)
	return out


def sync_grn_entry_details_for_pass(pass_unique_key: str):
	"""Refresh Entry Details on existing GRNs whenever a source Entry is saved."""
	key = (pass_unique_key or "").strip()
	if not key:
		return

	grn_names = frappe.get_all(
		"GRN Note",
		filters={"pass_unique_key": key, "docstatus": ["<", 2]},
		pluck="name",
	)
	if not grn_names:
		return

	entry_rows = _entry_rows_for_pass(key)
	for name in grn_names:
		grn = frappe.get_doc("GRN Note", name)
		grn.set("entry_details", [])
		for values in entry_rows:
			child = grn.append("entry_details", {})
			for fieldname, value in values.items():
				child.set(fieldname, value)
		grn.flags.ignore_validate = True
		grn.save(ignore_permissions=True, ignore_version=True)


def _transit_pass_payload(pass_unique_key: str) -> dict:
	key = (pass_unique_key or "").strip()
	if not key:
		return {}
	tp = frappe.db.get_value(
		"PPAS Transit Pass",
		{"pass_unique_key": key},
		[
			"season",
			"transit_pass_no",
			"transit_pass_date",
			"quantity",
			"pacs",
			"ppc",
		],
		as_dict=True,
	)
	if not tp:
		return {}
	return {
		"cmr_season": (tp.season or "").strip(),
		"transit_pass_no": tp.transit_pass_no,
		"transit_pass_date": tp.transit_pass_date,
		"tp_quantity": flt(tp.quantity),
		"pacs": (tp.pacs or "").strip(),
		"ppc": (tp.ppc or "").strip(),
		"entry_details": _entry_rows_for_pass(key),
	}


def _grn_details_from_rst(rst_no: str, pass_unique_key: str | None = None) -> dict:
	rst_no = (rst_no or "").strip()
	wbm_name = _resolve_wbm_for_rst(rst_no, pass_unique_key)
	if not wbm_name:
		return {"error": _("No Weigh Bridge Measurement found for RST No {0}.").format(rst_no)}

	doc = frappe.new_doc("GRN Note")
	doc.pass_unique_key = (pass_unique_key or "").strip()
	doc.rst_no = rst_no
	doc._apply_weigh_bridge(wbm_name)
	if doc.quality_check:
		doc._apply_quality_check(doc.quality_check)
	if doc.gate_entry:
		doc._apply_gate_entry(doc.gate_entry)

	return {
		"weigh_bridge_measurement": wbm_name,
		"gross_vehicle_weight": doc.gross_vehicle_weight,
		"gross_weight": doc.gross_weight,
		"tare_weight": doc.tare_weight,
		"net_weight": doc.net_weight,
		"gunny_type": doc.gunny_type,
		"gunny_weight": doc.gunny_weight,
		"gate_entry": doc.gate_entry,
		"vehicle_no": doc.vehicle_no,
		"driver_name": doc.driver_name,
		"arrival_date": doc.arrival_date,
		"arrival_time": doc.arrival_time,
		"gate_out_time": doc.gate_out_time,
		"quality_check": doc.quality_check,
		"qc_sample_no": doc.qc_sample_no,
		"no_of_bags": doc.no_of_bags,
		"moisture": doc.moisture,
		"dust": doc.dust,
		"unloader_name": doc.unloader_name,
		"unloading_point": doc.unloading_point,
		"ppc_name": doc.ppc_name,
		"paddy_type": doc.paddy_type,
		"paddy_quality": doc.paddy_quality,
		"qc_decision": doc.qc_decision,
		"paddy_received_in_pkt": doc.paddy_received_in_pkt,
		"paddy_returned": doc.paddy_returned,
		"qc_bag_details": [
			{
				"jute_pkt_no": cint(row.jute_pkt_no),
				"no_of_plastic_bag": cint(row.no_of_plastic_bag),
			}
			for row in (doc.qc_bag_details or [])
		],
	}


@frappe.whitelist()
def get_transit_pass_details(pass_unique_key):
	return _transit_pass_payload(pass_unique_key)


@frappe.whitelist()
def get_grn_details_from_rst(rst_no, pass_unique_key=None):
	return _grn_details_from_rst(rst_no, pass_unique_key)


@frappe.whitelist()
def get_rst_no_autocomplete(txt="", pass_unique_key="", limit=25):
	txt = (txt or "").strip()
	pass_unique_key = (pass_unique_key or "").strip()
	limit = cint(limit) or 25

	conditions = ["IFNULL(rst_no, '') != ''"]
	values: list = []
	if pass_unique_key:
		conditions.append("pass_unique_key = %s")
		values.append(pass_unique_key)
	if txt:
		conditions.append("rst_no LIKE %s")
		values.append(f"%{txt}%")
	values.append(limit)

	rows = frappe.db.sql(
		f"""
		SELECT DISTINCT rst_no
		FROM `tabWeigh Bridge Measurement`
		WHERE {" AND ".join(conditions)}
		ORDER BY rst_no
		LIMIT %s
		""",
		tuple(values),
		pluck=True,
	)
	return [{"value": row, "label": row, "description": ""} for row in rows]
