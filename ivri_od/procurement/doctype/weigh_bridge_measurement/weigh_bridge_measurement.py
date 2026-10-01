# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from ivri_od.procurement.bag_balance import get_weigh_bridge_bags_for_tp
from ivri_od.procurement.doctype.rst_details.rst_details import (
	get_rst_agent_name,
	is_private_procurement_rst,
)
from ivri_od.procurement.mill_gate import (
	get_open_gate_entry_in_for_vehicle,
	get_vehicles_inside_mill,
	get_qc_for_vehicle_open_visit,
	get_qc_sl_no,
	get_quality_check_for_vehicle_open_visit,
	get_weighment_vehicles_inside_mill,
	normalize_vehicle_no,
)


PENDING_QC = "Pending QC"
KG_PER_QUINTAL = 100
QTY_MAX_DECIMALS = 3


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

	lines = frappe.get_all(
		"Quality Check Bag Detail",
		filters={
			"parent": qc_name,
			"parenttype": "Quality Check",
			"parentfield": "type_of_pkt",
		},
		fields=["jute_pkt_no", "no_of_plastic_bag", "jute_bags", "plastic_bags"],
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


class WeighBridgeMeasurement(Document):
	def after_insert(self):
		# Create the GRN when a newly inserted WBM is already eligible.
		_ensure_grn_note_for_weigh_bridge(self.name)

	def on_update(self):
		# Recheck when RST adds a TP key or tare/QC values make this WBM eligible.
		_ensure_grn_note_for_weigh_bridge(self.name)

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
		self._apply_rst_private_procurement_mode()
		self._sync_source_mode_fields()
		self._sync_agent_name_from_rst_details()
		self._validate_pass_unique_key()
		self._validate_farmer_or_agent_source()
		self._normalize_truck_numbers()
		self._sync_actual_truck()
		self._sync_quality_check_link()
		self._sync_gate_entry_link()
		self._sync_bag_details_from_qc()
		self._sync_gunny_type_fields()
		self._update_weights()
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

	def _apply_rst_private_procurement_mode(self):
		rst_link = (self.demo_rst_data or "").strip()
		if not rst_link or not frappe.db.exists("RST Details", rst_link):
			return
		rst = frappe.get_doc("RST Details", rst_link)
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
		else:
			agent = get_rst_agent_name(demo_rst_data=rst_link, rst_no=self.rst_no)
			if agent:
				self.agent_name = agent

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
			row.weight_per_jute_kg = row_data["weight_per_jute_kg"]
			row.weight_per_plastic_kg = row_data["weight_per_plastic_kg"]
			row.jute_total_qt = row_data["jute_total_qt"]
			row.plastic_total_qt = row_data["plastic_total_qt"]
			row.gunny_weight_qt = row_data["gunny_weight_qt"]

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
		vehicle = get_effective_truck_no(self)
		if not vehicle:
			self.quality_check = ""
			self.quality_test = PENDING_QC
			self.slno_of_qc = 0
			self.gate_entry = ""
			return

		qc = get_qc_for_vehicle_open_visit(vehicle)
		if not qc:
			self.quality_check = ""
			self.quality_test = PENDING_QC
			self.slno_of_qc = 0
			return

		self.quality_check = qc.name
		self.slno_of_qc = get_qc_sl_no(qc.name)
		decision = (qc.qc_decision or "").strip()
		self.quality_test = decision if decision else PENDING_QC
		if cint(frappe.db.get_value("Quality Check", qc.name, "is_farmer_or_agent")):
			self.is_farmer_or_agent = 1

	def _sync_gate_entry_link(self):
		vehicle = get_effective_truck_no(self)
		if not vehicle:
			self.gate_entry = ""
			return
		self.gate_entry = resolve_gate_entry_for_wbm_vehicle(
			vehicle, self.quality_check
		)

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
			frappe.throw(
				_(
					"Enter Jute and/or Plastic weight per bag in Bag Details (from QC) for Gunny Cut."
				)
			)

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
		if table_qt > 0:
			return table_qt

		return 0.0

	def _update_weights(self):
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


def get_effective_truck_no(doc) -> str:
	if is_farmer_or_agent_source(doc):
		return normalize_vehicle_no(doc.get("actual_truck_no") or doc.get("vehicle_no"))
	actual = (doc.get("actual_truck_no") or "").strip().upper()
	if actual:
		return actual
	return (doc.get("truck_no_in_tp") or "").strip().upper()


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
):
	resolved = get_effective_truck_no(
		{
			"actual_truck_no": actual_truck_no,
			"truck_no_in_tp": truck_no_in_tp,
			"is_farmer_or_agent": is_farmer_or_agent,
			"vehicle_no": vehicle_no,
		}
	)
	if not resolved:
		return {
			"quality_check": "",
			"quality_test": PENDING_QC,
			"vehicle_no": "",
			"slno_of_qc": 0,
			"bag_details": [],
			"gate_entry": "",
		}

	qc = get_qc_for_vehicle_open_visit(resolved)
	linked_qc = (quality_check or "").strip()
	if not qc and wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		linked_qc = linked_qc or (
			frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "quality_check") or ""
		).strip()

	if not qc and linked_qc and frappe.db.exists("Quality Check", linked_qc):
		row = frappe.db.get_value(
			"Quality Check",
			linked_qc,
			["name", "vehicle_no", "qc_decision"],
			as_dict=True,
		)
		if row and (row.vehicle_no or "").strip().upper() == resolved:
			qc = row

	if not qc:
		return {
			"quality_check": "",
			"quality_test": PENDING_QC,
			"vehicle_no": resolved,
			"slno_of_qc": 0,
			"bag_details": [],
			"gate_entry": resolve_gate_entry_for_wbm_vehicle(resolved, linked_qc),
		}

	decision = (qc.qc_decision or "").strip()
	saved_rows: list[dict] = []
	if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		doc = frappe.get_doc("Weigh Bridge Measurement", wbm_name)
		saved_rows = _saved_bag_weights(doc.bag_weight_details)
	bag_details = build_bag_details_from_qc(qc.name, saved_rows)
	qc_modified = frappe.db.get_value("Quality Check", qc.name, "modified")
	qc_name = (getattr(qc, "name", None) or "").strip()
	gate_entry = resolve_gate_entry_for_wbm_vehicle(resolved, qc_name)
	return {
		"quality_check": qc.name,
		"quality_test": decision if decision else PENDING_QC,
		"vehicle_no": resolved,
		"slno_of_qc": get_qc_sl_no(qc.name),
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


def sync_weigh_bridge_quality_for_vehicle(
	vehicle_no: str,
	*,
	quality_check: str = "",
	quality_test: str = PENDING_QC,
):
	"""Update all WBM rows whose effective truck matches this vehicle."""
	vehicle_no = (vehicle_no or "").strip().upper()
	if not vehicle_no:
		return

	names = frappe.db.sql(
		"""
		SELECT name
		FROM `tabWeigh Bridge Measurement`
		WHERE UPPER(TRIM(IFNULL(actual_truck_no, ''))) = %s
			OR (
				IFNULL(actual_truck_no, '') = ''
				AND UPPER(TRIM(IFNULL(truck_no_in_tp, ''))) = %s
			)
		""",
		(vehicle_no, vehicle_no),
		pluck=True,
	)
	if not names:
		return

	for name in names:
		frappe.db.set_value(
			"Weigh Bridge Measurement",
			name,
			{
				"quality_check": quality_check or "",
				"quality_test": quality_test or PENDING_QC,
				"slno_of_qc": get_qc_sl_no(quality_check) if quality_check else 0,
			},
			update_modified=False,
		)
		if quality_check:
			_ensure_wbm_bag_details_from_qc(name)
		_ensure_grn_note_for_weigh_bridge(name)


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

	_ensure_grn_note_for_weigh_bridge(name)

	_ensure_wbm_bag_details_from_qc(name, data)
	return data


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


def _ensure_grn_note_for_weigh_bridge(wbm_name: str):
	"""Create one GRN Note on WBM creation when the load is eligible."""
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return
	if frappe.db.exists("GRN Note", {"weigh_bridge_measurement": wbm_name}):
		return

	local = is_local_procurement_wbm(wbm_name)
	if local:
		_create_local_grn_for_wbm(wbm_name)
		return

	wbm = frappe.db.get_value(
		"Weigh Bridge Measurement",
		wbm_name,
		[
			"quality_test",
			"pass_unique_key",
			"rst_no",
			"tare_weight",
			"is_farmer_or_agent",
			"agent_name",
			"demo_rst_data",
		],
		as_dict=True,
	)
	if not wbm or wbm.quality_test not in ("Accepted", "Partially Accepted"):
		return
	if not flt(wbm.tare_weight):
		return
	if not (wbm.rst_no or "").strip():
		return
	if not (wbm.pass_unique_key or "").strip():
		return

	try:
		farmer_agent = cint(wbm.is_farmer_or_agent)
		agent_name = (wbm.agent_name or "").strip() or get_rst_agent_name(
			demo_rst_data=wbm.demo_rst_data, rst_no=wbm.rst_no
		) or ""
		grn = frappe.get_doc(
			{
				"doctype": "GRN Note",
				"pass_unique_key": (wbm.pass_unique_key or "").strip(),
				"rst_no": wbm.rst_no,
				"weigh_bridge_measurement": wbm_name,
				"is_local_procurement": 0,
				"is_farmer_or_agent": 1 if farmer_agent else 0,
				"agent_name": agent_name if farmer_agent else "",
			}
		)
		grn.insert(ignore_permissions=True)
	except Exception as exc:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Automatic GRN Note creation failed for {wbm_name}",
		)
		frappe.msgprint(
			_("Quality Test is accepted, but the GRN Note could not be created: {0}").format(str(exc)),
			title=_("Automatic GRN Note Error"),
			indicator="red",
			alert=True,
		)


def _create_local_grn_for_wbm(wbm_name: str):
	from ivri_od.procurement.doctype.grn_note.grn_note import grn_dict_for_local_wbm

	payload = grn_dict_for_local_wbm(wbm_name)
	if not payload:
		return
	try:
		grn = frappe.get_doc(payload)
		grn.flags.auto_local_grn = True
		grn.insert(ignore_permissions=True)
	except Exception as exc:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Automatic local GRN Note creation failed for {wbm_name}",
		)
		frappe.msgprint(
			_("Weigh Bridge was saved, but the local GRN Note could not be created: {0}").format(
				str(exc)
			),
			title=_("Automatic GRN Note Error"),
			indicator="red",
			alert=True,
		)


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
def get_pass_unique_key_autocomplete(txt="", limit=25):
	txt = (txt or "").strip()
	limit = frappe.utils.cint(limit) or 25
	conditions = "IFNULL(pass_unique_key, '') != ''"
	values = [limit]
	if txt:
		conditions += " AND pass_unique_key LIKE %s"
		values.insert(0, f"%{txt}%")

	keys = frappe.db.sql(
		f"""
		SELECT pass_unique_key
		FROM `tabPPAS Transit Pass`
		WHERE {conditions}
		ORDER BY pass_unique_key
		LIMIT %s
		""",
		tuple(values),
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
