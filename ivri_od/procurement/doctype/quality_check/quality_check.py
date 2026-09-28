# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from ivri_od.procurement.mill_gate import GATE_ENTRY_INSIDE_MILL, get_open_gate_entry_in_for_vehicle, is_gate_in_inside_mill
from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	PENDING_QC,
	sync_weigh_bridge_quality_for_vehicle,
)


def is_farmer_or_agent_qc(doc) -> bool:
	return bool(cint(doc.get("is_farmer_or_agent")))


class QualityCheck(Document):
	def validate(self):
		self._sync_farmer_or_agent_mode()
		self._validate_gate_entry()
		self._validate_party_name()
		self._validate_qc_decision()
		self._normalize_fields()
		self._validate_type_of_pkt()

	def on_update(self):
		_sync_weigh_bridge_quality_from_qc(self)

	def _validate_gate_entry(self):
		gate_entry = (self.gate_entry or "").strip()
		self.gate_entry = gate_entry
		vehicle = (self.vehicle_no or "").strip().upper()
		self.vehicle_no = vehicle

		if not vehicle:
			frappe.throw(_("Select Vehicle No (from gate in records)."))

		if not gate_entry:
			gate_entry = _find_gate_entry_for_vehicle(vehicle, exclude_qc=self.name)
			if not gate_entry:
				frappe.throw(_gate_entry_lookup_error(vehicle, exclude_qc=self.name))
			self.gate_entry = gate_entry

		if not frappe.db.exists("Gate Entry", gate_entry):
			frappe.throw(_("Gate Entry {0} does not exist.").format(frappe.bold(gate_entry)))

		ge = frappe.db.get_value(
			"Gate Entry",
			gate_entry,
			["vehicle_no", "driver_name", "in_out"],
			as_dict=True,
		)
		if not ge or not (ge.vehicle_no or "").strip():
			frappe.throw(_("Selected Gate Entry has no Vehicle No."))

		if ge.in_out != "In":
			frappe.throw(_("Quality Check is allowed only for Gate Entry marked In."))

		if not is_gate_in_inside_mill(gate_entry):
			frappe.throw(
				_("This vehicle visit is already closed (Gate Out recorded). Start a new Gate In for a new Quality Check."),
				title=_("Visit Closed"),
			)

		ge_vehicle = ge.vehicle_no.strip().upper()
		if ge_vehicle != vehicle:
			frappe.throw(
				_("Vehicle No {0} does not match Gate Entry vehicle {1}.").format(
					frappe.bold(vehicle),
					frappe.bold(ge_vehicle),
				)
			)

		self.vehicle_no = ge_vehicle
		if not (self.driver_name or "").strip():
			self.driver_name = (ge.driver_name or "").strip()
		else:
			self.driver_name = self.driver_name.strip()

		existing = frappe.db.get_value(
			"Quality Check",
			{"gate_entry": gate_entry},
			"name",
		)
		if existing and existing != self.name:
			frappe.throw(
				_("Quality Check already exists for this vehicle gate entry ({0}).").format(
					frappe.bold(existing),
				),
				title=_("Duplicate Vehicle"),
			)

	def _sync_farmer_or_agent_mode(self):
		if is_farmer_or_agent_qc(self):
			self.party_name = ""
			self.society_name = ""
			self.unloading_point = ""
			self.staff_name = ""
		else:
			self.farmer_name = ""

	def _normalize_fields(self):
		if self.staff_name:
			self.staff_name = self.staff_name.strip()
		if self.unloading_point:
			self.unloading_point = self.unloading_point.strip()
		if self.farmer_name:
			self.farmer_name = self.farmer_name.strip()

	def _validate_party_name(self):
		if is_farmer_or_agent_qc(self):
			farmer = (self.farmer_name or "").strip()
			self.farmer_name = farmer
			if not farmer:
				frappe.throw(_("Enter Farmer Name."))
			return

		party = (self.party_name or "").strip()
		self.party_name = party
		if not party:
			frappe.throw(_("Select PPC Name."))
		if not frappe.db.exists("PPC Master", party):
			frappe.throw(_("PPC Name {0} is not in PPC Master.").format(frappe.bold(party)))

	def _validate_qc_decision(self):
		decision = (self.qc_decision or "").strip()
		self.qc_decision = decision
		if not decision:
			frappe.throw(_("Select Quality Test (Accepted, Partially Accepted, or Rejected)."))
		if decision not in ("Accepted", "Partially Accepted", "Rejected"):
			frappe.throw(_("Invalid Quality Test."))

	def _validate_type_of_pkt(self):
		rows = [row for row in (self.type_of_pkt or []) if row.jute_pkt_no or row.no_of_plastic_bag]
		if not rows:
			frappe.throw(_("Add at least one row in Type of Bags (Jute Bag No / No of Plastic Bag)."))


def _sync_weigh_bridge_quality_from_qc(doc):
	vehicle = (doc.vehicle_no or "").strip().upper()
	if not vehicle:
		return
	decision = (doc.qc_decision or "").strip() or PENDING_QC
	sync_weigh_bridge_quality_for_vehicle(vehicle, quality_check=doc.name, quality_test=decision)


def _find_gate_entry_for_vehicle(vehicle_no: str, exclude_qc: str | None = None) -> str | None:
	vehicle_no = (vehicle_no or "").strip().upper()
	if not vehicle_no:
		return None

	exclude_qc = (exclude_qc or "").strip()
	if exclude_qc and not frappe.db.exists("Quality Check", exclude_qc):
		exclude_qc = ""

	qc_exclude = ""
	values: list = [vehicle_no]
	if exclude_qc:
		qc_exclude = "AND qc.name != %s"
		values.append(exclude_qc)

	rows = frappe.db.sql(
		f"""
		SELECT ge.name
		FROM `tabGate Entry` ge
		WHERE ge.in_out = 'In'
			AND UPPER(TRIM(ge.vehicle_no)) = %s
			AND {GATE_ENTRY_INSIDE_MILL}
			AND NOT EXISTS (
				SELECT 1
				FROM `tabQuality Check` qc
				WHERE qc.gate_entry = ge.name
					{qc_exclude}
			)
		ORDER BY ge.entry_date DESC, ge.entry_time DESC, ge.creation DESC
		LIMIT 1
		""",
		tuple(values),
		pluck=True,
	)
	return rows[0] if rows else None


def _gate_entry_lookup_error(vehicle_no: str, exclude_qc: str | None = None) -> str:
	vehicle_no = (vehicle_no or "").strip().upper()
	ge = frappe.db.get_value(
		"Gate Entry",
		{"in_out": "In", "vehicle_no": vehicle_no},
		["name", "vehicle_no"],
		as_dict=True,
	)
	if not ge:
		ge = frappe.db.sql(
			"""
			SELECT name, vehicle_no
			FROM `tabGate Entry`
			WHERE in_out = 'In' AND UPPER(TRIM(vehicle_no)) = %s
			ORDER BY entry_date DESC, entry_time DESC, creation DESC
			LIMIT 1
			""",
			vehicle_no,
			as_dict=True,
		)
		ge = ge[0] if ge else None

	if not ge:
		return _("No Gate Entry (In) found for Vehicle No {0}.").format(frappe.bold(vehicle_no))

	if not frappe.db.sql(
		f"""
		SELECT 1 FROM `tabGate Entry` ge
		WHERE ge.name = %s AND {GATE_ENTRY_INSIDE_MILL}
		""",
		ge.name,
	):
		return _("Vehicle {0} is not inside the mill (Gate In already closed).").format(
			frappe.bold(vehicle_no)
		)

	existing_qc = frappe.db.get_value("Quality Check", {"gate_entry": ge.name}, "name")
	if existing_qc and existing_qc != (exclude_qc or "").strip():
		return _("Quality Check {0} already exists for this vehicle (Gate Entry {1}).").format(
			frappe.bold(existing_qc),
			frappe.bold(ge.name),
		)

	return _("No open Gate Entry (In) found for Vehicle No {0}.").format(frappe.bold(vehicle_no))


@frappe.whitelist()
def get_vehicle_no_autocomplete(txt="", limit=25, exclude_qc=None):
	txt = (txt or "").strip().upper()
	limit = cint(limit) or 25
	exclude_qc = (exclude_qc or "").strip()
	if exclude_qc and not frappe.db.exists("Quality Check", exclude_qc):
		exclude_qc = ""

	qc_exclude = ""
	values: list = []
	if exclude_qc:
		qc_exclude = "AND qc.name != %s"
		values.append(exclude_qc)

	conditions = [
		"ge.in_out = 'In'",
		"IFNULL(ge.vehicle_no, '') != ''",
		GATE_ENTRY_INSIDE_MILL,
		f"""NOT EXISTS (
			SELECT 1 FROM `tabQuality Check` qc
			WHERE qc.gate_entry = ge.name {qc_exclude}
		)""",
	]
	if txt:
		conditions.append("UPPER(TRIM(ge.vehicle_no)) LIKE %s")
		values.append(f"%{txt}%")

	values.append(limit)

	vehicles = frappe.db.sql(
		f"""
		SELECT DISTINCT UPPER(TRIM(ge.vehicle_no)) AS vehicle_no
		FROM `tabGate Entry` ge
		WHERE {" AND ".join(conditions)}
		ORDER BY vehicle_no
		LIMIT %s
		""",
		tuple(values),
		pluck=True,
	)
	return [{"value": v, "label": v, "description": ""} for v in vehicles]


@frappe.whitelist()
def resolve_gate_entry_for_vehicle(vehicle_no, exclude_qc=None):
	vehicle_no = (vehicle_no or "").strip().upper()
	if not vehicle_no:
		return {"error": _("Enter Vehicle No.")}

	gate_entry = _find_gate_entry_for_vehicle(vehicle_no, exclude_qc=exclude_qc)
	if not gate_entry:
		return {"error": _gate_entry_lookup_error(vehicle_no, exclude_qc=exclude_qc)}

	ge = frappe.db.get_value(
		"Gate Entry",
		gate_entry,
		["driver_name", "vehicle_no"],
		as_dict=True,
	)
	return {
		"gate_entry": gate_entry,
		"vehicle_no": (ge.vehicle_no or vehicle_no).strip().upper(),
		"driver_name": (ge.driver_name or "").strip(),
	}
