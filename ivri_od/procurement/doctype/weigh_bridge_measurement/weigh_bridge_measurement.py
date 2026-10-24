# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_datetime, get_time, getdate

from ivri_od.procurement.datetime_fields import ensure_doc_datetime

from ivri_od.procurement.bag_balance import get_weigh_bridge_bags_for_tp
from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass
from ivri_od.procurement.doctype.rst_details.rst_details import (
	get_rst_agent_name,
	is_private_procurement_rst,
)
from ivri_od.procurement.mill_gate import (
	get_open_gate_entry_in_for_vehicle,
	get_vehicles_inside_mill,
	get_qc_for_vehicle_open_visit,
	get_quality_check_for_vehicle,
	get_qc_sl_no,
	get_quality_check_for_vehicle_open_visit,
	get_weighment_vehicles_inside_mill,
	is_gate_in_inside_mill,
	normalize_vehicle_no,
)


PENDING_QC = "Pending QC"
REJECTED_QC = "Rejected"
KG_PER_QUINTAL = 100
QTY_MAX_DECIMALS = 3


def effective_quality_test_for_wbm(
	qc_name: str,
	*,
	tare_weight=None,
	wbm_name: str | None = None,
) -> str:
	qc_name = (qc_name or "").strip()
	if not qc_name or not frappe.db.exists("Quality Check", qc_name):
		return PENDING_QC

	decision = (frappe.db.get_value("Quality Check", qc_name, "qc_decision") or "").strip()
	if not decision:
		return PENDING_QC

	tare = flt(tare_weight)
	if not tare and wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		tare = flt(frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "tare_weight"))

	if tare:
		from ivri_od.procurement.doctype.quality_check.quality_check import (
			is_full_paddy_return_from_qc,
		)

		if is_full_paddy_return_from_qc(qc_name):
			return REJECTED_QC

	if decision in ("Accepted", "Partially Accepted"):
		return decision
	return PENDING_QC


def apply_wbm_quality_outcome_from_qc(doc) -> None:
	qc_name = (doc.quality_check or "").strip()
	if not qc_name:
		return
	doc.quality_test = effective_quality_test_for_wbm(
		qc_name,
		tare_weight=doc.tare_weight,
		wbm_name=doc.name if not doc.is_new() else None,
	)
	if doc.quality_test == REJECTED_QC:
		doc.net_weight = 0


def persist_wbm_quality_and_net_after_qc_sync(wbm_name: str) -> None:
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return
	doc = frappe.get_doc("Weigh Bridge Measurement", wbm_name)
	doc._update_weights()
	apply_wbm_quality_outcome_from_qc(doc)
	frappe.db.set_value(
		"Weigh Bridge Measurement",
		wbm_name,
		{"quality_test": doc.quality_test, "net_weight": doc.net_weight, "deduction": doc.deduction},
		update_modified=True,
	)


def _trim_qty(value, max_decimals: int = QTY_MAX_DECIMALS) -> float:
	"""Round then drop trailing zeros (0.250 -> 0.25)."""
	v = flt(value, max_decimals)
	if not v:
		return 0.0
	text = f"{v:.{max_decimals}f}".rstrip("0").rstrip(".")
	return flt(text or 0)


def _qc_bag_line_values(line) -> tuple[int, int]:
	if isinstance(line, dict):
		jute = cint(line.get("jute_pkt_no"))
		plastic = cint(line.get("no_of_plastic_bag"))
		if not jute:
			jute = cint(line.get("jute_bags"))
		if not plastic:
			plastic = cint(line.get("plastic_bags"))
		return jute, plastic
	jute = cint(getattr(line, "jute_pkt_no", None))
	plastic = cint(getattr(line, "no_of_plastic_bag", None))
	if not jute:
		jute = cint(getattr(line, "jute_bags", None))
	if not plastic:
		plastic = cint(getattr(line, "plastic_bags", None))
	return jute, plastic


def _qc_bag_lines(qc_name: str) -> list[dict]:
	qc_name = (qc_name or "").strip()
	if not qc_name or not frappe.db.exists("Quality Check", qc_name):
		return []

	fields = ["jute_pkt_no", "no_of_plastic_bag"]
	if frappe.db.has_column("Quality Check Bag Detail", "jute_bags"):
		fields.append("jute_bags")
	if frappe.db.has_column("Quality Check Bag Detail", "plastic_bags"):
		fields.append("plastic_bags")

	lines = frappe.get_all(
		"Quality Check Bag Detail",
		filters={
			"parent": qc_name,
			"parenttype": "Quality Check",
			"parentfield": "type_of_pkt",
		},
		fields=fields,
		order_by="idx asc",
	)
	if lines:
		return [
			{"jute_pkt_no": j, "no_of_plastic_bag": p}
			for line in lines
			for j, p in [_qc_bag_line_values(line)]
			if j or p
		]

	qc = frappe.get_doc("Quality Check", qc_name)
	out = []
	for row in qc.type_of_pkt or []:
		jute, plastic = _qc_bag_line_values(row)
		if jute or plastic:
			out.append({"jute_pkt_no": jute, "no_of_plastic_bag": plastic})
	return out


def _update_bag_line_totals(row) -> float:
	jute_kg = flt(getattr(row, "weight_per_jute_kg", 0)) * cint(getattr(row, "jute_bags", 0))
	plastic_kg = flt(getattr(row, "weight_per_plastic_kg", 0)) * cint(getattr(row, "plastic_bags", 0))
	row.total_bags = cint(getattr(row, "jute_bags", 0)) + cint(getattr(row, "plastic_bags", 0))
	row.jute_total_qt = _trim_qty(jute_kg / KG_PER_QUINTAL)
	row.plastic_total_qt = _trim_qty(plastic_kg / KG_PER_QUINTAL)
	row.gunny_weight_qt = _trim_qty(flt(row.jute_total_qt) + flt(row.plastic_total_qt))
	return flt(row.gunny_weight_qt)


def _saved_bag_weights(rows) -> list[dict]:
	saved = []
	for row in rows or []:
		saved.append(
			{
				"weight_per_jute_kg": _trim_qty(getattr(row, "weight_per_jute_kg", None)),
				"weight_per_plastic_kg": _trim_qty(getattr(row, "weight_per_plastic_kg", None)),
			}
		)
	return saved


def build_bag_details_from_qc(
	qc_name: str, saved_rows: list[dict] | None = None
) -> list[dict]:
	qc_name = (qc_name or "").strip()
	if not qc_name or not frappe.db.exists("Quality Check", qc_name):
		return []

	saved_rows = saved_rows or []
	lines = _qc_bag_lines(qc_name)
	out = []
	for i, line in enumerate(lines):
		saved = saved_rows[i] if i < len(saved_rows) else {}
		jute_bags, plastic_bags = _qc_bag_line_values(line)
		w_jute = _trim_qty(saved.get("weight_per_jute_kg"))
		w_plastic = _trim_qty(saved.get("weight_per_plastic_kg"))
		jute_qt = _trim_qty(w_jute * jute_bags / KG_PER_QUINTAL)
		plastic_qt = _trim_qty(w_plastic * plastic_bags / KG_PER_QUINTAL)
		out.append(
			{
				"jute_bags": jute_bags,
				"plastic_bags": plastic_bags,
				"total_bags": jute_bags + plastic_bags,
				"weight_per_jute_kg": w_jute,
				"weight_per_plastic_kg": w_plastic,
				"jute_total_qt": jute_qt,
				"plastic_total_qt": plastic_qt,
				"gunny_weight_qt": _trim_qty(jute_qt + plastic_qt),
			}
		)
	return out


def is_farmer_or_agent_source(doc) -> bool:
	return bool(cint(doc.get("is_farmer_or_agent")))


TP_STATUS_RECEIVED = "TP Received"
TP_STATUS_NOT_RECEIVED = "TP Not Received"
TP_STATUS_PPC_MISMATCH = "PPC Mismatch"
TP_STATUS_LOCAL = "Local Procurement"
TP_STATUS_RICE_DISPATCH = "Rice Dispatch"


def compute_wbm_tp_status(doc) -> str:
	"""RST party on transit pass but no TP No → TP Not Received; pass linked → TP Received."""
	from ivri_od.procurement.doctype.rst_details.rst_details import (
		is_private_procurement_rst,
		party_found_awaiting_tp,
	)

	rst_link = (getattr(doc, "demo_rst_data", None) or "").strip()
	if rst_link and frappe.db.exists("RST Details", rst_link):
		rst = frappe.get_doc("RST Details", rst_link)
		if (rst.tp_status or "") == TP_STATUS_RICE_DISPATCH:
			return TP_STATUS_RICE_DISPATCH
		if is_private_procurement_rst(rst):
			return TP_STATUS_LOCAL
		if party_found_awaiting_tp(rst):
			return TP_STATUS_NOT_RECEIVED
		if (getattr(doc, "pass_unique_key", None) or "").strip():
			return TP_STATUS_RECEIVED
		if (rst.tp_status or "") == TP_STATUS_PPC_MISMATCH:
			return TP_STATUS_PPC_MISMATCH
		if (rst.tp_no or "").strip() and (rst.tp_status or "") != "Invalid TP No":
			return TP_STATUS_RECEIVED
		return TP_STATUS_NOT_RECEIVED

	if cint(getattr(doc, "is_farmer_or_agent", 0)) and not (
		getattr(doc, "pass_unique_key", None) or ""
	).strip():
		return TP_STATUS_LOCAL
	if (getattr(doc, "pass_unique_key", None) or "").strip():
		return TP_STATUS_RECEIVED
	if rst_link:
		return TP_STATUS_NOT_RECEIVED
	return ""


class WeighBridgeMeasurement(Document):
	def after_insert(self):
		# Create the GRN when a newly inserted WBM is already eligible.
		_ensure_grn_note_for_weigh_bridge(self.name)
		wbm_name = self.name
		frappe.db.after_commit(lambda: _ensure_grn_note_for_weigh_bridge(wbm_name))
		self._schedule_procurement_rollup_sync()

	def on_update(self):
		# Recheck when RST adds a TP key or tare/QC values make this WBM eligible.
		_ensure_grn_note_for_weigh_bridge(self.name)
		self._schedule_procurement_rollup_sync()
		self._refresh_pass_left_after_correction()

	def _refresh_pass_left_after_correction(self):
		"""TP No / PPC corrected: the pass this weighment left must drop it from its totals."""
		before = self.get_doc_before_save()
		old_key = ((before.pass_unique_key if before else "") or "").strip()
		if not old_key or old_key == (self.pass_unique_key or "").strip():
			return
		frappe.db.after_commit(lambda k=old_key: _sync_procurement_rollups_for_pass(k))
		frappe.db.after_commit(lambda k=old_key: refresh_tp_fulfillment_for_pass(k))

	def _schedule_procurement_rollup_sync(self):
		# Rice Dispatch has no Transit Pass, so it never feeds Transit Pass totals.
		if is_farmer_or_agent_source(self) or (self.tp_status or "") == TP_STATUS_RICE_DISPATCH:
			return
		key = (self.pass_unique_key or "").strip()
		if not key:
			return
		frappe.db.after_commit(lambda k=key: _sync_procurement_rollups_for_pass(k))
		frappe.db.after_commit(lambda k=key: refresh_tp_fulfillment_for_pass(k))

	def on_trash(self):
		if self.demo_rst_data and frappe.db.exists("RST Details", self.demo_rst_data):
			if (
				frappe.db.get_value(
					"RST Details", self.demo_rst_data, "weigh_bridge_measurement"
				)
				== self.name
			):
				frappe.db.set_value(
					"RST Details",
					self.demo_rst_data,
					"weigh_bridge_measurement",
					None,
					update_modified=False,
				)

	def validate(self):
		ensure_doc_datetime(self, "date", default_now=True)
		self._sync_and_validate_weighment()
		self._sync_weighment_datetime()
		self._apply_rst_private_procurement_mode()
		self._sync_rst_no_from_rst_details()
		self._sync_tp_status()
		self._sync_source_mode_fields()
		self._sync_agent_name_from_rst_details()
		self._validate_pass_unique_key()
		self._validate_farmer_or_agent_source()
		self._normalize_truck_numbers()
		self._sync_actual_truck()

	def _sync_and_validate_weighment(self):
		self._sync_gate_entry_link()
		self._sync_quality_check_link()
		self._sync_bag_details_from_qc()
		self._sync_gunny_type_fields()
		self._update_weights()
		apply_wbm_quality_outcome_from_qc(self)
		self._validate_weigh_bridge_bags()
		self._validate_bag_detail_weights()
		self._validate_quality_and_tare()
		self._validate_actual_truck_weighment()

	def _sync_source_mode_fields(self):
		if is_farmer_or_agent_source(self):
			self.pass_unique_key = ""
			self.transit_pass_no = ""
			self.tp_weight = 0
			self.truck_no_in_tp = ""
			self.same_truck_as_transit_pass = 0
			self.pacs_name = ""
			if not (self.actual_truck_no or "").strip() and (self.vehicle_no or "").strip():
				self.actual_truck_no = normalize_vehicle_no(self.vehicle_no)
			self.vehicle_no = ""
		else:
			self.vehicle_no = ""
			self.agent_name = ""

	def _sync_rst_no_from_rst_details(self):
		rst_link = (self.demo_rst_data or "").strip()
		if not rst_link or not frappe.db.exists("RST Details", rst_link):
			return
		rst_no = (frappe.db.get_value("RST Details", rst_link, "rst_no") or "").strip()
		if rst_no:
			self.rst_no = rst_no

	def _sync_tp_status(self):
		self.tp_status = compute_wbm_tp_status(self)

	def _sync_weighment_datetime(self):
		ensure_doc_datetime(self, "date", default_now=True)
		if not self.date:
			return
		dt = get_datetime(self.date)
		if self.meta.has_field("measurement_date"):
			self.measurement_date = getdate(dt)
		if self.meta.has_field("measurement_time"):
			self.measurement_time = get_time(dt).replace(microsecond=0)

	def _apply_rst_private_procurement_mode(self):
		rst_link = (self.demo_rst_data or "").strip()
		if not rst_link or not frappe.db.exists("RST Details", rst_link):
			return
		rst = frappe.get_doc("RST Details", rst_link)
		if (rst.tp_status or "") == TP_STATUS_RICE_DISPATCH:
			self._apply_rst_rice_dispatch_mode(rst)
			return
		if not is_private_procurement_rst(rst):
			return
		self.is_farmer_or_agent = 1
		self.pass_unique_key = ""
		self.transit_pass_no = ""
		self.tp_weight = 0
		self.truck_no_in_tp = ""
		self.same_truck_as_transit_pass = 0
		self.pacs_name = ""
		self.vehicle_no = ""
		rst_vehicle = normalize_vehicle_no(rst.vehicle_no)
		if rst_vehicle:
			self.actual_truck_no = rst_vehicle
		if is_private_procurement_rst(rst):
			self.agent_name = ""
			if (rst.party_name or "").strip():
				self.party_name = rst.party_name.strip()
			if (rst.local_purchase_order or "").strip():
				self.local_purchase_order = rst.local_purchase_order.strip()
				if hasattr(self, "purchase_order"):
					self.purchase_order = rst.local_purchase_order.strip()
		else:
			agent = get_rst_agent_name(demo_rst_data=rst_link, rst_no=self.rst_no)
			if agent:
				self.agent_name = agent

	def _apply_rst_rice_dispatch_mode(self, rst):
		"""Rice Dispatch: no Transit Pass, no agent. RST TP No is kept here as the Lot No / reference."""
		self.is_farmer_or_agent = 0
		self.pass_unique_key = ""
		self.transit_pass_no = ""
		self.tp_weight = 0
		self.truck_no_in_tp = ""
		self.pacs_name = ""
		self.vehicle_no = ""
		self.agent_name = ""
		self.party_name = (rst.party_name or "").strip()
		self.lot_no = rst.tp_no or ""
		rst_vehicle = normalize_vehicle_no(rst.vehicle_no)
		self.actual_truck_no = rst_vehicle
		self.same_truck_as_transit_pass = 1 if rst_vehicle else 0

	def _sync_agent_name_from_rst_details(self):
		if not is_farmer_or_agent_source(self):
			return
		rst_link = (self.demo_rst_data or "").strip()
		if rst_link and frappe.db.exists("RST Details", rst_link):
			rst = frappe.get_doc("RST Details", rst_link)
			if is_private_procurement_rst(rst):
				self.agent_name = ""
				return
		agent = get_rst_agent_name(demo_rst_data=self.demo_rst_data, rst_no=self.rst_no)
		if agent:
			self.agent_name = agent

	def _validate_farmer_or_agent_source(self):
		if not is_farmer_or_agent_source(self):
			return
		vehicle = normalize_vehicle_no(self.actual_truck_no)
		if not vehicle:
			frappe.throw(_("Enter Actual Truck No."))
		self.actual_truck_no = vehicle
		self.vehicle_no = ""
		if self.demo_rst_data and frappe.db.exists("RST Details", self.demo_rst_data):
			self.agent_name = ""
		elif not (self.agent_name or "").strip():
			frappe.throw(_("Select Agent Name for farmer / agent procurement."))
		# Local procurement from RST: WBM is created before gate/QC; gate is linked when available.
		if self.demo_rst_data and frappe.db.exists("RST Details", self.demo_rst_data):
			return
		if not get_open_gate_entry_in_for_vehicle(vehicle):
			frappe.throw(
				_("Vehicle {0} has no open Gate Entry (In) inside the mill.").format(
					frappe.bold(vehicle)
				)
			)

	def _validate_pass_unique_key(self):
		if is_farmer_or_agent_source(self):
			return
		key = (self.pass_unique_key or "").strip()
		self.pass_unique_key = key
		# RST can create a WBM before the agent provides the transit pass.
		if not key and self.demo_rst_data and frappe.db.exists("RST Details", self.demo_rst_data):
			return
		if not key:
			frappe.throw(_("Select Pass Unique Key from PPAS Transit Pass."))

		if not frappe.db.exists("PPAS Transit Pass", {"pass_unique_key": key}):
			frappe.throw(
				_("No PPAS Transit Pass found for Pass Unique Key {0}.").format(frappe.bold(key))
			)

		tp = frappe.db.get_value(
			"PPAS Transit Pass",
			{"pass_unique_key": key},
			["name", "transit_pass_no", "vehicle_no", "bags", "pacs", "quantity"],
			as_dict=True,
		)
		if tp:
			self.transit_pass_no = tp.transit_pass_no
			self.pacs_name = tp.pacs
			self.tp_weight = flt(tp.quantity)
			if tp.vehicle_no:
				self.truck_no_in_tp = tp.vehicle_no.strip().upper()
			if not self.no_of_bags and tp.bags:
				self.no_of_bags = tp.bags

	def _sync_bag_details_from_qc(self):
		qc_name = (self.quality_check or "").strip()
		if not qc_name:
			self.bag_weight_details = []
			self._sync_total_bags_from_qc_table()
			return

		saved = _saved_bag_weights(self.bag_weight_details)
		rows = build_bag_details_from_qc(qc_name, saved)
		if not rows:
			return

		self.bag_weight_details = []
		for row_data in rows:
			row = self.append("bag_weight_details", {})
			row.jute_bags = row_data["jute_bags"]
			row.plastic_bags = row_data["plastic_bags"]
			row.total_bags = row_data["total_bags"]
			row.weight_per_jute_kg = row_data["weight_per_jute_kg"]
			row.weight_per_plastic_kg = row_data["weight_per_plastic_kg"]
			row.jute_total_qt = row_data["jute_total_qt"]
			row.plastic_total_qt = row_data["plastic_total_qt"]
			row.gunny_weight_qt = row_data["gunny_weight_qt"]
		self._sync_total_bags_from_qc_table()

	def _persist_bag_details_from_qc(self):
		"""Write QC bag lines to DB without blocking on Gunny Cut weight validation."""
		if not (self.quality_check or "").strip():
			return
		if not build_bag_details_from_qc(self.quality_check, _saved_bag_weights(self.bag_weight_details)):
			return
		self._sync_bag_details_from_qc()
		self.flags.ignore_validate = True
		self.save(ignore_permissions=True)

	def _update_bag_line_gunny(self):
		for row in self.bag_weight_details or []:
			_update_bag_line_totals(row)
			row.weight_per_jute_kg = _trim_qty(row.weight_per_jute_kg)
			row.weight_per_plastic_kg = _trim_qty(row.weight_per_plastic_kg)

	def _sync_quality_check_link(self):
		qc = self._resolve_quality_check_for_wbm()
		if not qc:
			self.quality_check = ""
			self.quality_test = PENDING_QC
			self.slno_of_qc = 0
			return

		qc_name = qc.get("name") if isinstance(qc, dict) else qc.name
		self.quality_check = qc_name
		self.slno_of_qc = get_qc_sl_no(qc_name)
		self.quality_test = effective_quality_test_for_wbm(
			qc_name,
			tare_weight=self.tare_weight,
			wbm_name=self.name if not self.is_new() else None,
		)
		if cint(frappe.db.get_value("Quality Check", qc_name, "is_farmer_or_agent")):
			self.is_farmer_or_agent = 1

	def _resolve_quality_check_for_wbm(self):
		gate_entry = (self.gate_entry or "").strip()
		if gate_entry:
			rows = frappe.get_all(
				"Quality Check",
				filters={"gate_entry": gate_entry},
				fields=["name", "qc_decision"],
				order_by="modified desc, creation desc",
				limit=1,
			)
			if rows:
				return rows[0]

		for vehicle in _qc_lookup_vehicle_candidates(self):
			qc = get_quality_check_for_vehicle(vehicle)
			if qc:
				return qc
		return None

	def _vehicle_corrected(self) -> bool:
		before = self.get_doc_before_save()
		return bool(before) and _qc_lookup_vehicle_candidates(before) != _qc_lookup_vehicle_candidates(self)

	def _sync_gate_entry_link(self):
		gate_entry = ""
		# A corrected Vehicle No must not keep the Quality Check / visit of the wrong vehicle.
		quality_check = None if self._vehicle_corrected() else self.quality_check
		for vehicle in _qc_lookup_vehicle_candidates(self):
			gate_entry = resolve_gate_entry_for_wbm_vehicle(vehicle, quality_check)
			if gate_entry:
				break
		self.gate_entry = gate_entry or ""

	def _normalize_truck_numbers(self):
		if self.truck_no_in_tp:
			self.truck_no_in_tp = self.truck_no_in_tp.strip().upper()
		if self.actual_truck_no:
			self.actual_truck_no = self.actual_truck_no.strip().upper()
		if self.vehicle_no:
			self.vehicle_no = normalize_vehicle_no(self.vehicle_no)
		if self.rst_no:
			self.rst_no = self.rst_no.strip()

	def _sync_actual_truck(self):
		if is_farmer_or_agent_source(self):
			return

		rst_link = (self.demo_rst_data or "").strip()
		pass_key = (self.pass_unique_key or "").strip()

		if rst_link and pass_key and frappe.db.exists("RST Details", rst_link):
			rst_v = (
				frappe.db.get_value("RST Details", rst_link, "vehicle_no") or ""
			).strip().upper()
			tp_v = (self.truck_no_in_tp or "").strip().upper()
			if not tp_v and pass_key:
				tp_v = (
					frappe.db.get_value(
						"PPAS Transit Pass", {"pass_unique_key": pass_key}, "vehicle_no"
					)
					or ""
				).strip().upper()

			if rst_v and tp_v:
				if rst_v == tp_v:
					self.same_truck_as_transit_pass = 0
					self.actual_truck_no = ""
				else:
					self.same_truck_as_transit_pass = 1
					self.actual_truck_no = rst_v
			elif rst_v and not tp_v:
				self.same_truck_as_transit_pass = 1
				self.actual_truck_no = rst_v
			elif not self.same_truck_as_transit_pass:
				self.actual_truck_no = ""
		else:
			if not self.same_truck_as_transit_pass:
				self.actual_truck_no = ""

	def _validate_actual_truck_weighment(self):
		if is_farmer_or_agent_source(self):
			return
		if self.demo_rst_data:
			return
		if not self.same_truck_as_transit_pass:
			return
		actual = normalize_vehicle_no(self.actual_truck_no)
		if not actual:
			frappe.throw(_("Select Actual Truck No from Going to Weighment vehicles."))
		allowed = set(get_weighment_vehicles_inside_mill(limit=500))
		if actual not in allowed:
			frappe.throw(
				_(
					"Vehicle {0} is not on an open Gate Entry with Going to Weighment."
				).format(frappe.bold(actual))
			)

	def _validate_weigh_bridge_bags(self):
		if self.demo_rst_data:
			return
		if is_farmer_or_agent_source(self):
			return
		if not self.pass_unique_key or not self.no_of_bags:
			return

		tp_bags = cint(
			frappe.db.get_value(
				"PPAS Transit Pass",
				{"pass_unique_key": self.pass_unique_key},
				"bags",
			)
		)
		if not tp_bags:
			return

		total_wbm = get_weigh_bridge_bags_for_tp(self.pass_unique_key, exclude_wbm=self.name)
		total_wbm += cint(self.no_of_bags)
		if total_wbm > tp_bags:
			frappe.throw(
				_(
					"No. of Bags on weigh bridge for this TP ({0}) cannot exceed Total Bags on TP ({1})."
				).format(total_wbm, tp_bags)
			)

	def _total_bags_from_qc_table(self) -> int:
		total = 0
		for row in self.bag_weight_details or []:
			total += cint(row.jute_bags) + cint(row.plastic_bags)
		return total

	def _sync_total_bags_from_qc_table(self):
		self.total_bags = self._total_bags_from_qc_table()

	def _validate_bag_detail_weights(self):
		if self.demo_rst_data:
			return
		if (self.gunny_type or "").strip() != "Gunny Cut":
			return

		qc_name = (self.quality_check or "").strip()
		rows = self.bag_weight_details or []
		if not rows and qc_name and _qc_bag_lines(qc_name):
			frappe.throw(
				_(
					"Bag Details (from QC) is required for Gunny Cut. Refresh bag lines from Quality Check and enter weights."
				)
			)

		for idx, row in enumerate(rows, start=1):
			jute_bags = cint(row.jute_bags)
			plastic_bags = cint(row.plastic_bags)
			if jute_bags and flt(row.weight_per_jute_kg) <= 0:
				frappe.throw(
					_(
						"Bag Details row {0}: enter Jute Wt (KG/Bag) when Jute Bags are present."
					).format(idx)
				)
			if plastic_bags and flt(row.weight_per_plastic_kg) <= 0:
				frappe.throw(
					_(
						"Bag Details row {0}: enter Plastic Wt (KG/Bag) when Plastic Bags are present."
					).format(idx)
				)

		if rows and self._total_bags_from_qc_table() > 0 and flt(self.gunny_weight) <= 0:
			frappe.throw(_("Enter Gunny Weight (QT) or bag weights in Bag Details for Gunny Cut."))

	def _sync_gunny_type_fields(self):
		gunny_type = (self.gunny_type or "").strip()
		self.gunny_type = gunny_type
		if gunny_type == "Gunny Gross":
			self.gunny_weight = 0

	def _gunny_weight_from_bag_table(self) -> float:
		total_jute = 0.0
		total_plastic = 0.0
		for row in self.bag_weight_details or []:
			jute_qt = flt(flt(row.weight_per_jute_kg) * cint(row.jute_bags) / KG_PER_QUINTAL, 3)
			plastic_qt = flt(
				flt(row.weight_per_plastic_kg) * cint(row.plastic_bags) / KG_PER_QUINTAL, 3
			)
			row.jute_total_qt = _trim_qty(jute_qt)
			row.plastic_total_qt = _trim_qty(plastic_qt)
			row.gunny_weight_qt = _trim_qty(jute_qt + plastic_qt)
			total_jute += jute_qt
			total_plastic += plastic_qt
		self.total_jute_empty_qt = flt(total_jute, 3)
		self.total_plastic_empty_qt = flt(total_plastic, 3)
		return flt(total_jute + total_plastic, 3)

	def _resolve_gunny_weight_qt(self) -> float:
		if self.demo_rst_data:
			self.total_jute_empty_qt = 0
			self.total_plastic_empty_qt = 0
			return flt(
				frappe.db.get_value("RST Details", self.demo_rst_data, "gunny_weight_qt")
			)

		if (self.gunny_type or "").strip() != "Gunny Cut":
			self.total_jute_empty_qt = 0
			self.total_plastic_empty_qt = 0
			return 0.0

		table_qt = self._gunny_weight_from_bag_table()
		manual = flt(self.gunny_weight)
		if manual > 0:
			return manual
		return table_qt

	def _sync_deduction(self):
		"""Deduction (QT): RST Details value if entered, else Quality Check Dust (Kg) converted to quintal.

		RST-linked weighments always follow this rule, so a correction in RST Details or Quality Check
		replaces the old value. A manual weighment only gets the Quality Check dust while Deduction is empty.
		"""
		rst_link = (self.get("demo_rst_data") or "").strip()
		rst_deduction = 0.0
		if rst_link and frappe.db.exists("RST Details", rst_link):
			rst_deduction = flt(frappe.db.get_value("RST Details", rst_link, "deduction_qt"))
		if rst_deduction > 0:
			self.deduction = rst_deduction
			return

		if not rst_link and flt(self.deduction) > 0:
			return
		qc_name = (self.get("quality_check") or "").strip()
		dust_kg = flt(frappe.db.get_value("Quality Check", qc_name, "dust")) if qc_name else 0.0
		# 100 kg = 1 quintal
		self.deduction = flt(dust_kg / 100, 3) if dust_kg > 0 else 0

	def _update_weights(self):
		self._sync_deduction()
		self._sync_total_bags_from_qc_table()
		load_weight = flt(self.load_weight)
		tare_weight = flt(self.tare_weight)

		if load_weight and tare_weight:
			self.gross_weight = load_weight - tare_weight
		elif load_weight:
			self.gross_weight = load_weight
		else:
			self.gross_weight = 0

		self.gunny_weight = flt(self._resolve_gunny_weight_qt(), 3)
		gunny_weight = flt(self.gunny_weight)
		deduction = flt(self.deduction)
		self.net_weight = flt(max(flt(self.gross_weight) - gunny_weight - deduction, 0), 3)

	def _validate_quality_and_tare(self):
		gunny_type = (self.gunny_type or "").strip()
		if not gunny_type:
			frappe.throw(_("Select Gunny Type (Gunny Gross or Gunny Cut)."))

		if (
			not is_farmer_or_agent_source(self)
			and self.same_truck_as_transit_pass
			and not self.actual_truck_no
		):
			frappe.throw(_("Enter Actual Truck No when it differs from the Transit Pass."))


def _qc_lookup_vehicle_candidates(doc) -> list[str]:
	"""Truck numbers to match Quality Check / Gate Entry (actual truck first when different from TP)."""
	seen: set[str] = set()
	out: list[str] = []
	raw_order = (
		(doc.get("actual_truck_no"), doc.get("truck_no_in_tp"))
		if cint(doc.get("same_truck_as_transit_pass"))
		else (doc.get("truck_no_in_tp"), doc.get("actual_truck_no"))
	) + (doc.get("vehicle_no"),)
	for raw in raw_order:
		v = normalize_vehicle_no(raw)
		if v and v not in seen:
			seen.add(v)
			out.append(v)
	return out


def get_effective_truck_no(doc) -> str:
	if is_farmer_or_agent_source(doc):
		return normalize_vehicle_no(doc.get("actual_truck_no") or doc.get("vehicle_no"))
	candidates = _qc_lookup_vehicle_candidates(doc)
	return candidates[0] if candidates else ""


def resolve_gate_entry_for_wbm_vehicle(
	vehicle_no: str, quality_check: str | None = None
) -> str:
	"""Open visit Gate Entry for the effective WBM vehicle (from QC or Gate In)."""
	vehicle_no = normalize_vehicle_no(vehicle_no)
	if not vehicle_no:
		return ""

	qc = get_qc_for_vehicle_open_visit(vehicle_no)
	if qc and (qc.gate_entry or "").strip():
		return qc.gate_entry.strip()

	qc_name = (quality_check or "").strip()
	if qc_name and frappe.db.exists("Quality Check", qc_name):
		linked = (frappe.db.get_value("Quality Check", qc_name, "gate_entry") or "").strip()
		if linked:
			return linked

	return get_open_gate_entry_in_for_vehicle(vehicle_no) or ""


def get_quality_check_for_vehicle(vehicle_no: str) -> str | None:
	return get_quality_check_for_vehicle_open_visit(vehicle_no)


def get_qc_serial_for_vehicle(vehicle_no: str) -> int:
	from ivri_od.procurement.mill_gate import get_qc_serial_for_vehicle as _impl

	return _impl(vehicle_no)


@frappe.whitelist()
def get_weighment_vehicle_autocomplete(txt="", limit=25):
	"""Actual Truck No options: Gate In + Going to Weighment + inside mill."""
	vehicles = get_weighment_vehicles_inside_mill(txt=txt, limit=limit)
	return [{"value": v, "label": v, "description": ""} for v in vehicles]


@frappe.whitelist()
def get_farmer_vehicle_autocomplete(txt="", limit=25):
	"""Farmer/agent Vehicle No: open Gate Entry (In) still inside the mill."""
	vehicles = get_vehicles_inside_mill(txt=txt, limit=limit)
	return [{"value": v, "label": v, "description": ""} for v in vehicles]


@frappe.whitelist()
def get_quality_check_for_wbm(
	actual_truck_no=None,
	truck_no_in_tp=None,
	wbm_name=None,
	quality_check=None,
	is_farmer_or_agent=None,
	vehicle_no=None,
	same_truck_as_transit_pass=None,
):
	lookup_doc = {
		"actual_truck_no": actual_truck_no,
		"truck_no_in_tp": truck_no_in_tp,
		"is_farmer_or_agent": is_farmer_or_agent,
		"vehicle_no": vehicle_no,
		"same_truck_as_transit_pass": same_truck_as_transit_pass,
	}

	wbm_gate = ""
	if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		wbm_gate = (frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "gate_entry") or "").strip()

	if wbm_gate:
		qc_by_gate = frappe.db.get_value(
			"Quality Check",
			{"gate_entry": wbm_gate},
			["name", "vehicle_no", "qc_decision"],
			as_dict=True,
		)
		if qc_by_gate:
			return _quality_check_payload_for_wbm(
				qc_by_gate.name,
				normalize_vehicle_no(qc_by_gate.vehicle_no) or get_effective_truck_no(lookup_doc),
				wbm_name,
				wbm_gate,
			)

	resolved = get_effective_truck_no(lookup_doc)
	linked_qc = (quality_check or "").strip()
	if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		linked_qc = linked_qc or (
			frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "quality_check") or ""
		).strip()

	qc = None
	matched_vehicle = resolved
	for vehicle in _qc_lookup_vehicle_candidates(lookup_doc):
		qc = get_quality_check_for_vehicle(vehicle)
		if qc:
			matched_vehicle = normalize_vehicle_no(qc.get("vehicle_no")) or vehicle
			break

	if not qc and linked_qc and frappe.db.exists("Quality Check", linked_qc):
		return _quality_check_payload_for_wbm(
			linked_qc, matched_vehicle or resolved, wbm_name, wbm_gate
		)

	if not qc:
		fallback_vehicle = resolved or (_qc_lookup_vehicle_candidates(lookup_doc) or [""])[0]
		return {
			"quality_check": "",
			"quality_test": PENDING_QC,
			"vehicle_no": fallback_vehicle,
			"slno_of_qc": 0,
			"bag_details": [],
			"gate_entry": resolve_gate_entry_for_wbm_vehicle(fallback_vehicle, linked_qc)
			if fallback_vehicle
			else "",
		}

	qc_name = (qc.get("name") or "").strip()
	return _quality_check_payload_for_wbm(qc_name, matched_vehicle, wbm_name, wbm_gate)


def _quality_check_payload_for_wbm(
	qc_name: str,
	resolved_vehicle: str,
	wbm_name: str | None,
	preferred_gate: str = "",
) -> dict:
	saved_rows: list[dict] = []
	if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		doc = frappe.get_doc("Weigh Bridge Measurement", wbm_name)
		saved_rows = _saved_bag_weights(doc.bag_weight_details)
	quality_test = effective_quality_test_for_wbm(
		qc_name,
		tare_weight=frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "tare_weight")
		if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name)
		else None,
		wbm_name=wbm_name,
	)
	bag_details = build_bag_details_from_qc(qc_name, saved_rows)
	qc_modified = frappe.db.get_value("Quality Check", qc_name, "modified")
	gate_entry = (preferred_gate or "").strip() or resolve_gate_entry_for_wbm_vehicle(
		resolved_vehicle, qc_name
	)
	return {
		"quality_check": qc_name,
		"quality_test": quality_test,
		"vehicle_no": resolved_vehicle,
		"slno_of_qc": get_qc_sl_no(qc_name),
		"bag_details": bag_details,
		"qc_modified": str(qc_modified) if qc_modified else "",
		"gate_entry": gate_entry,
	}


@frappe.whitelist()
def get_bag_details_from_qc(quality_check, wbm_name=None):
	"""QC bag lines for the grid; keeps entered weights from saved WBM."""
	qc_name = (quality_check or "").strip()
	if not qc_name:
		return []

	saved_rows: list[dict] = []
	if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		doc = frappe.get_doc("Weigh Bridge Measurement", wbm_name)
		saved_rows = _saved_bag_weights(doc.bag_weight_details)

	return build_bag_details_from_qc(qc_name, saved_rows)


def _wbm_names_matching_vehicle(vehicle_no: str) -> list[str]:
	vehicle_no = normalize_vehicle_no(vehicle_no)
	if not vehicle_no:
		return []
	return frappe.db.sql(
		"""
		SELECT name
		FROM `tabWeigh Bridge Measurement`
		WHERE UPPER(TRIM(IFNULL(actual_truck_no, ''))) = %s
			OR UPPER(TRIM(IFNULL(truck_no_in_tp, ''))) = %s
			OR UPPER(TRIM(IFNULL(vehicle_no, ''))) = %s
		""",
		(vehicle_no, vehicle_no, vehicle_no),
		pluck=True,
	)


def find_wbm_names_for_quality_sync(vehicle_no: str, quality_check: str = "") -> list[str]:
	"""WBMs for this QC: same vehicle on any truck field, or same gate entry as QC."""
	names: set[str] = set(_wbm_names_matching_vehicle(vehicle_no))
	qc_name = (quality_check or "").strip()
	if not qc_name or not frappe.db.exists("Quality Check", qc_name):
		return list(names)

	gate_entry = (frappe.db.get_value("Quality Check", qc_name, "gate_entry") or "").strip()
	if gate_entry:
		names.update(
			frappe.get_all(
				"Weigh Bridge Measurement",
				filters={"gate_entry": gate_entry},
				pluck="name",
			)
		)
		ge_vehicle = frappe.db.get_value("Gate Entry", gate_entry, "vehicle_no")
		if ge_vehicle:
			names.update(_wbm_names_matching_vehicle(ge_vehicle))
	return list(names)


def sync_weigh_bridge_quality_for_vehicle(
	vehicle_no: str,
	*,
	quality_check: str = "",
	quality_test: str = PENDING_QC,
):
	"""Update WBM rows linked to this vehicle / gate entry when Quality Check changes."""
	vehicle_no = normalize_vehicle_no(vehicle_no)
	names = find_wbm_names_for_quality_sync(vehicle_no, quality_check)
	if not names:
		return

	gate_entry = ""
	if quality_check and frappe.db.exists("Quality Check", quality_check):
		gate_entry = (frappe.db.get_value("Quality Check", quality_check, "gate_entry") or "").strip()

	for name in names:
		effective_test = quality_test or PENDING_QC
		if quality_check:
			effective_test = effective_quality_test_for_wbm(quality_check, wbm_name=name)
		values = {
			"quality_check": quality_check or "",
			"quality_test": effective_test,
			"slno_of_qc": get_qc_sl_no(quality_check) if quality_check else 0,
		}
		if gate_entry:
			values["gate_entry"] = gate_entry
		frappe.db.set_value("Weigh Bridge Measurement", name, values, update_modified=True)
		if quality_check:
			_ensure_wbm_bag_details_from_qc(name)
		persist_wbm_quality_and_net_after_qc_sync(name)
		_ensure_grn_note_for_weigh_bridge(name)


def unlink_quality_check_from_weigh_bridge(quality_check: str, keep_gate_entry: str = "") -> list[str]:
	"""A Quality Check was moved to another vehicle visit: weighments of the old visit go back to Pending QC.

	Their GRN Notes are synced too, so the wrong Quality Check values leave the final GRN.
	"""
	quality_check = (quality_check or "").strip()
	if not quality_check:
		return []
	names = frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"quality_check": quality_check, "gate_entry": ["!=", (keep_gate_entry or "").strip()]},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value(
			"Weigh Bridge Measurement",
			name,
			{"quality_check": "", "quality_test": PENDING_QC, "slno_of_qc": 0},
			update_modified=True,
		)
		persist_wbm_quality_and_net_after_qc_sync(name)
		_ensure_grn_note_for_weigh_bridge(name)
	return names


@frappe.whitelist()
def persist_quality_check_sync(name, actual_truck_no=None, truck_no_in_tp=None):
	"""Write Quality Check link and Quality Test to DB so list view matches QC."""
	name = (name or "").strip()
	if not name or not frappe.db.exists("Weigh Bridge Measurement", name):
		return {}

	row = None
	if actual_truck_no is None and truck_no_in_tp is None:
		row = frappe.db.get_value(
			"Weigh Bridge Measurement",
			name,
			["actual_truck_no", "truck_no_in_tp", "is_farmer_or_agent", "vehicle_no"],
			as_dict=True,
		)
		actual_truck_no = row.actual_truck_no if row else ""
		truck_no_in_tp = row.truck_no_in_tp if row else ""
	else:
		row = frappe.db.get_value(
			"Weigh Bridge Measurement",
			name,
			["is_farmer_or_agent", "vehicle_no"],
			as_dict=True,
		)

	data = get_quality_check_for_wbm(
		actual_truck_no=actual_truck_no,
		truck_no_in_tp=truck_no_in_tp,
		wbm_name=name,
		is_farmer_or_agent=row.is_farmer_or_agent if row else 0,
		vehicle_no=row.vehicle_no if row else "",
	)
	current = frappe.db.get_value(
		"Weigh Bridge Measurement",
		name,
		["quality_check", "quality_test"],
		as_dict=True,
	)
	if not current:
		return data

	quality_unchanged = (current.quality_check or "") == (data.get("quality_check") or "") and (
		current.quality_test or ""
	) == (data.get("quality_test") or "")
	slno = cint(data.get("slno_of_qc"))
	current_slno = cint(frappe.db.get_value("Weigh Bridge Measurement", name, "slno_of_qc") or 0)

	if not quality_unchanged or current_slno != slno:
		frappe.db.set_value(
			"Weigh Bridge Measurement",
			name,
			{
				"quality_check": data.get("quality_check") or "",
				"quality_test": data.get("quality_test") or PENDING_QC,
				"slno_of_qc": slno,
				"gate_entry": data.get("gate_entry") or "",
			},
			update_modified=False,
		)
	elif (data.get("gate_entry") or "") != (
		frappe.db.get_value("Weigh Bridge Measurement", name, "gate_entry") or ""
	):
		frappe.db.set_value(
			"Weigh Bridge Measurement",
			name,
			{"gate_entry": data.get("gate_entry") or ""},
			update_modified=False,
		)

	persist_wbm_quality_and_net_after_qc_sync(name)
	_ensure_grn_note_for_weigh_bridge(name)

	_ensure_wbm_bag_details_from_qc(name, data)
	return data


def is_rice_dispatch_wbm(wbm_name: str) -> bool:
	"""Rice Dispatch weighment: never turned into a GRN Note and not part of Transit Pass totals."""
	if not wbm_name:
		return False
	return frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "tp_status") == TP_STATUS_RICE_DISPATCH


def is_local_procurement_wbm(wbm_name: str) -> bool:
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return False
	row = frappe.db.get_value(
		"Weigh Bridge Measurement",
		wbm_name,
		["is_farmer_or_agent", "pass_unique_key"],
		as_dict=True,
	)
	return bool(cint(row.is_farmer_or_agent)) and not (row.pass_unique_key or "").strip()


def wbm_gate_entry_in(wbm_name: str) -> str:
	"""Gate In of the visit this weighment belongs to.

	Its Gate Entry link, else (older WBMs saved without one) the same vehicle's latest Gate In
	before the weighment.
	"""
	row = frappe.db.get_value(
		"Weigh Bridge Measurement",
		wbm_name,
		["gate_entry", "actual_truck_no", "truck_no_in_tp", "vehicle_no", "same_truck_as_transit_pass", "creation"],
		as_dict=True,
	)
	if not row:
		return ""
	gate_entry = (row.gate_entry or "").strip()
	if gate_entry:
		if frappe.db.get_value("Gate Entry", gate_entry, "in_out") == "Out":
			return (frappe.db.get_value("Gate Entry", gate_entry, "gate_entry_in") or "").strip()
		return gate_entry
	for vehicle in _qc_lookup_vehicle_candidates(row):
		found = frappe.db.sql(
			"""
			SELECT name FROM `tabGate Entry`
			WHERE in_out = 'In' AND UPPER(TRIM(vehicle_no)) = %s AND creation <= %s
			ORDER BY creation DESC
			LIMIT 1
			""",
			(vehicle, row.creation),
		)
		if found:
			return found[0][0]
	return ""


def wbm_vehicle_has_exited(wbm_name: str) -> bool:
	"""True when the visit of this weighment has a Gate Exit (vehicle has left the mill)."""
	gate_in = wbm_gate_entry_in(wbm_name)
	if not gate_in or frappe.db.get_value("Gate Entry", gate_in, "in_out") != "In":
		return False
	return not is_gate_in_inside_mill(gate_in)


def create_grn_notes_after_gate_exit(gate_entry_in: str) -> list[str]:
	"""Create GRN Notes for the weighments of this visit; called when the vehicle exits.

	Returns the GRN Notes created now (existing ones are only synced).
	"""
	gate_entry_in = (gate_entry_in or "").strip()
	gate_in = frappe.db.get_value("Gate Entry", gate_entry_in, ["vehicle_no", "creation"], as_dict=True)
	if not gate_in:
		return []

	names = frappe.get_all("Weigh Bridge Measurement", filters={"gate_entry": gate_entry_in}, pluck="name")
	vehicle = normalize_vehicle_no(gate_in.vehicle_no)
	if vehicle:
		# WBMs saved without a gate link: same vehicle, weighed after this Gate In.
		unlinked = frappe.get_all(
			"Weigh Bridge Measurement",
			filters={"gate_entry": ["in", ["", None]], "creation": [">=", gate_in.creation]},
			fields=["name", "actual_truck_no", "truck_no_in_tp", "vehicle_no", "same_truck_as_transit_pass"],
		)
		names += [row.name for row in unlinked if vehicle in _qc_lookup_vehicle_candidates(row)]

	created = []
	for name in dict.fromkeys(names):
		if wbm_gate_entry_in(name) != gate_entry_in:
			continue  # belongs to a later visit of the same vehicle
		grn_filters = {"weigh_bridge_measurement": name, "docstatus": ["<", 2]}
		existed = frappe.db.exists("GRN Note", grn_filters)
		_ensure_grn_note_for_weigh_bridge(name)
		grn_name = frappe.db.get_value("GRN Note", grn_filters, "name")
		if grn_name and not existed:
			created.append(grn_name)
	return created


def _ensure_grn_note_for_weigh_bridge(wbm_name: str):
	"""Create or update GRN Note when the WBM is eligible (RST-linked or manual entry).

	A new GRN Note is created only after the vehicle's Gate Exit; an existing one keeps syncing.
	"""
	from ivri_od.procurement.doctype.grn_note.grn_note import (
		build_auto_grn_doc_dict,
		sync_grn_from_weigh_bridge,
	)

	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return

	if is_rice_dispatch_wbm(wbm_name):
		return

	# An existing GRN keeps syncing, local paddy purchase included, so a later correction reaches it.
	if frappe.db.exists(
		"GRN Note",
		{"weigh_bridge_measurement": wbm_name, "docstatus": ["<", 2]},
	):
		sync_grn_from_weigh_bridge(wbm_name)
		return

	if is_local_procurement_wbm(wbm_name):
		return

	# GRN is generated when the vehicle leaves, not at tare weight: Gate Exit calls this again.
	if not wbm_vehicle_has_exited(wbm_name):
		return

	payload = build_auto_grn_doc_dict(wbm_name)
	if not payload:
		return

	try:
		grn = frappe.get_doc(payload)
		grn.flags.auto_from_wbm = True
		if cint(payload.get("is_local_procurement")):
			grn.flags.auto_local_grn = True
		grn.insert(ignore_permissions=True)
	except Exception as exc:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Automatic GRN Note creation failed for {wbm_name}",
		)
		frappe.msgprint(
			_("Weigh Bridge was saved, but the GRN Note could not be created: {0}").format(str(exc)),
			title=_("Automatic GRN Note Error"),
			indicator="red",
			alert=True,
		)


def grn_pending_reasons_for_wbm(wbm_name: str) -> list[str]:
	reasons: list[str] = []
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return [_("Weigh Bridge Measurement not found.")]
	if frappe.db.exists(
		"GRN Note",
		{"weigh_bridge_measurement": wbm_name, "docstatus": ["<", 2]},
	):
		return []
	if is_rice_dispatch_wbm(wbm_name):
		return [_("Rice Dispatch is not linked to a GRN Note.")]

	wbm = frappe.db.get_value(
		"Weigh Bridge Measurement",
		wbm_name,
		["tare_weight", "pass_unique_key", "rst_no", "is_farmer_or_agent"],
		as_dict=True,
	)
	if not wbm:
		return [_("Weigh Bridge Measurement not found.")]
	if not flt(wbm.tare_weight):
		reasons.append(_("Enter tare weight on the weigh bridge."))
	if is_local_procurement_wbm(wbm_name):
		if not (wbm.rst_no or "").strip():
			reasons.append(_("Enter RST No."))
	else:
		if not (wbm.pass_unique_key or "").strip():
			reasons.append(_("Select Pass Unique Key."))
		if not (wbm.rst_no or "").strip():
			reasons.append(_("Enter RST No."))
		if not wbm_vehicle_has_exited(wbm_name):
			reasons.append(_("Vehicle has not exited yet. The GRN is created after Gate Exit."))
	return reasons


@frappe.whitelist()
def ensure_grn_note_for_weigh_bridge(wbm_name: str):
	"""Called after manual WBM save / QC sync so GRN is created when eligibility is met."""
	wbm_name = (wbm_name or "").strip()
	if not wbm_name:
		return {}
	_ensure_grn_note_for_weigh_bridge(wbm_name)
	grn_name = frappe.db.get_value(
		"GRN Note",
		{"weigh_bridge_measurement": wbm_name, "docstatus": ["<", 2]},
		"name",
	)
	pending = grn_pending_reasons_for_wbm(wbm_name) if not grn_name else []
	return {"grn_name": grn_name or "", "pending_reasons": pending, "synced": bool(grn_name)}


def _ensure_wbm_bag_details_from_qc(name: str, data: dict | None = None):
	"""Persist QC jute/plastic bag counts on WBM when missing or out of sync."""
	if not name or not frappe.db.exists("Weigh Bridge Measurement", name):
		return
	if data is None:
		row = frappe.db.get_value(
			"Weigh Bridge Measurement",
			name,
			["actual_truck_no", "truck_no_in_tp", "quality_check"],
			as_dict=True,
		)
		if not row:
			return
		data = get_quality_check_for_wbm(
			actual_truck_no=row.actual_truck_no,
			truck_no_in_tp=row.truck_no_in_tp,
			wbm_name=name,
			quality_check=row.quality_check,
		)

	qc_name = (data.get("quality_check") or "").strip()
	bag_details = data.get("bag_details") or []
	if not qc_name or not bag_details:
		return

	existing = frappe.get_all(
		"Weigh Bridge Bag Detail",
		filters={"parent": name, "parenttype": "Weigh Bridge Measurement", "parentfield": "bag_weight_details"},
		fields=["jute_bags", "plastic_bags"],
		order_by="idx asc",
	)
	if len(existing) == len(bag_details):
		in_sync = all(
			cint(existing[i].jute_bags) == cint(bag_details[i].get("jute_bags"))
			and cint(existing[i].plastic_bags) == cint(bag_details[i].get("plastic_bags"))
			for i in range(len(bag_details))
		)
		if in_sync:
			return

	try:
		doc = frappe.get_doc("Weigh Bridge Measurement", name)
		doc._persist_bag_details_from_qc()
	except Exception:
		frappe.log_error(title="WBM bag sync from QC")


@frappe.whitelist()
def refresh_wbm_bag_details_from_qc(name):
	"""Reload Bag Details child rows from linked Quality Check (keeps entered weights)."""
	name = (name or "").strip()
	if not name or not frappe.db.exists("Weigh Bridge Measurement", name):
		return {}

	row = frappe.db.get_value(
		"Weigh Bridge Measurement",
		name,
		["actual_truck_no", "truck_no_in_tp", "quality_check"],
		as_dict=True,
	)
	if not row:
		return {}

	data = get_quality_check_for_wbm(
		actual_truck_no=row.actual_truck_no,
		truck_no_in_tp=row.truck_no_in_tp,
		wbm_name=name,
		quality_check=row.quality_check,
	)
	_ensure_wbm_bag_details_from_qc(name, data)
	return data


@frappe.whitelist()
def get_pass_unique_key_autocomplete(txt="", limit=200, **kwargs):
	del kwargs
	txt = (txt or "").strip()
	limit = min(frappe.utils.cint(limit) or 200, 300)
	if txt:
		keys = frappe.db.sql(
			"""
			SELECT pass_unique_key
			FROM `tabPPAS Transit Pass`
			WHERE IFNULL(pass_unique_key, '') != ''
				AND (
					pass_unique_key LIKE %(txt)s
					OR IFNULL(transit_pass_no, '') LIKE %(txt)s
					OR IFNULL(ppc, '') LIKE %(txt)s
					OR name LIKE %(txt)s
				)
			ORDER BY
				CASE WHEN pass_unique_key = %(exact)s THEN 0 ELSE 1 END,
				pass_unique_key
			LIMIT %(limit)s
			""",
			{"txt": f"%{txt}%", "exact": txt, "limit": limit},
			pluck=True,
		)
	else:
		keys = frappe.db.sql(
			"""
			SELECT pass_unique_key
			FROM `tabPPAS Transit Pass`
			WHERE IFNULL(pass_unique_key, '') != ''
			ORDER BY pass_unique_key
			LIMIT %(limit)s
			""",
			{"limit": limit},
			pluck=True,
		)
	return [{"value": key, "label": key, "description": ""} for key in keys]


@frappe.whitelist()
def get_quality_status_for_rst(rst_no):
	"""Legacy API; prefer get_quality_check_for_wbm by vehicle."""
	rst_no = (rst_no or "").strip()
	if not rst_no:
		return {"quality_test": PENDING_QC}

	qc = frappe.db.get_value(
		"Quality Check",
		{"rst_no": rst_no},
		["qc_decision", "name"],
		as_dict=True,
	)
	if not qc or not (qc.qc_decision or "").strip():
		return {"quality_test": PENDING_QC, "quality_check": qc.name if qc else ""}

	return {
		"quality_test": qc.qc_decision.strip(),
		"quality_check": qc.name,
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def pass_unique_key_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link dropdown: show only pass unique key (document name), no extra columns."""
	del doctype, searchfield, filters  # legacy link query
	txt = f"%{txt}%" if txt else "%"
	start = frappe.utils.cint(start)
	page_len = frappe.utils.cint(page_len) or 20

	return frappe.db.sql(
		"""
		SELECT pass_unique_key
		FROM `tabPPAS Transit Pass`
		WHERE IFNULL(pass_unique_key, '') != ''
			AND pass_unique_key LIKE %s
		ORDER BY pass_unique_key
		LIMIT %s, %s
		""",
		(txt, start, page_len),
	)


def _sync_procurement_rollups_for_pass(pass_unique_key: str) -> None:
	from ivri_od.procurement.procurement_sync import sync_procurement_from_pass

	sync_procurement_from_pass((pass_unique_key or "").strip())
