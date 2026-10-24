# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from ivri_od.procurement.datetime_fields import ensure_doc_datetime
from ivri_od.procurement.mill_gate import GATE_ENTRY_INSIDE_MILL, get_open_gate_entry_in_for_vehicle, is_gate_in_inside_mill
from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	PENDING_QC,
	sync_weigh_bridge_quality_for_vehicle,
	unlink_quality_check_from_weigh_bridge,
)


def is_farmer_or_agent_qc(doc) -> bool:
	return bool(cint(doc.get("is_farmer_or_agent")))


def derive_qc_decision_from_returned_bags(paddy_returned) -> str:
	if cint(paddy_returned) <= 0:
		return "Accepted"
	return "Partially Accepted"


def is_full_paddy_return_from_qc(qc_name: str) -> bool:
	qc_name = (qc_name or "").strip()
	if not qc_name or not frappe.db.exists("Quality Check", qc_name):
		return False
	row = frappe.db.get_value(
		"Quality Check",
		qc_name,
		["paddy_returned", "paddy_received_in_pkt"],
		as_dict=True,
	)
	if not row:
		return False
	received = cint(row.paddy_received_in_pkt)
	returned = cint(row.paddy_returned)
	return received > 0 and returned >= received


class QualityCheck(Document):
	def validate(self):
		ensure_doc_datetime(
			self,
			"qc_datetime",
			default_now=True,
			date_field="qc_date",
			time_field="qc_time",
		)
		self._sync_farmer_or_agent_mode()
		self._validate_gate_entry()
		self._validate_farmer_or_agent_fields()
		self._sync_qc_decision_from_returned_bags()
		self._validate_qc_decision()
		self._normalize_fields()
		self._sync_paddy_type_from_old_new_bags()
		self._validate_old_new_bags()
		self._validate_type_of_pkt()

	def on_update(self):
		before = self.get_doc_before_save()
		if before and (before.gate_entry or "").strip() != (self.gate_entry or "").strip():
			# Vehicle corrected: weighments of the old visit must lose this Quality Check first.
			unlink_quality_check_from_weigh_bridge(self.name, self.gate_entry)
		_sync_weigh_bridge_quality_from_qc(self)

	def _validate_gate_entry(self):
		gate_entry = (self.gate_entry or "").strip()
		self.gate_entry = gate_entry
		vehicle = (self.vehicle_no or "").strip().upper()
		self.vehicle_no = vehicle

		# Editing a saved Quality Check later: the same vehicle keeps its visit, even after Gate Exit.
		# A corrected Vehicle No is matched to that vehicle's open Gate In again.
		before = self.get_doc_before_save()
		visit_unchanged = bool(before) and (before.vehicle_no or "").strip().upper() == vehicle
		if before and not visit_unchanged and gate_entry == (before.gate_entry or "").strip():
			gate_entry = self.gate_entry = ""

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

		if not visit_unchanged and not is_gate_in_inside_mill(gate_entry):
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

	def _validate_farmer_or_agent_fields(self):
		if is_farmer_or_agent_qc(self):
			farmer = (self.farmer_name or "").strip()
			self.farmer_name = farmer
			if not farmer:
				frappe.throw(_("Enter Farmer Name."))
			return

		staff = (self.staff_name or "").strip()
		self.staff_name = staff
		if not staff:
			frappe.throw(_("Enter Staff."))

		unloading = (self.unloading_point or "").strip()
		self.unloading_point = unloading
		if not unloading:
			frappe.throw(_("Enter Unloading Point."))

	def _sync_qc_decision_from_returned_bags(self):
		self.qc_decision = derive_qc_decision_from_returned_bags(self.paddy_returned)

	def _validate_qc_decision(self):
		decision = (self.qc_decision or "").strip()
		self.qc_decision = decision
		if not decision:
			frappe.throw(_("Quality Test could not be determined from returned bags."))
		if decision not in ("Accepted", "Partially Accepted"):
			frappe.throw(_("Invalid Quality Test."))

	def _sync_paddy_type_from_old_new_bags(self):
		filled = [row for row in (self.old_new_bags or []) if _is_old_new_bag_row_filled(row)]
		if len(filled) == 1:
			row = filled[0]
			self.paddy_type = _("Old {0}, New {1}").format(cint(row.old_bags), cint(row.new_bags))
		else:
			self.paddy_type = ""

	def _validate_old_new_bags(self):
		_validate_qc_child_table_single_filled_row(
			self.old_new_bags,
			_("Paddy Type (In Bags)"),
			_("Old Paddy Bags / New Paddy Bags"),
			_is_old_new_bag_row_filled,
		)

	def _validate_type_of_pkt(self):
		_validate_qc_child_table_single_filled_row(
			self.type_of_pkt,
			_("Type of Bags"),
			_("Jute Bag No / No of Plastic Bag"),
			_is_type_of_pkt_row_filled,
		)


def _is_old_new_bag_row_filled(row) -> bool:
	return bool(cint(row.old_bags) or cint(row.new_bags))


def _is_type_of_pkt_row_filled(row) -> bool:
	return bool(cint(row.jute_pkt_no) or cint(row.no_of_plastic_bag))


def _validate_qc_child_table_single_filled_row(rows, table_label, field_hint, is_filled):
	rows = list(rows or [])
	filled = [row for row in rows if is_filled(row)]

	if len(filled) > 1:
		frappe.throw(
			_("Only one row can be filled in {0}. Remove extra rows with data.").format(table_label)
		)

	if len(rows) > 1:
		frappe.throw(
			_("Only one row is allowed in {0}. Delete extra rows before saving.").format(table_label)
		)

	if not filled:
		frappe.throw(
			_("Enter one row in {0} ({1}).").format(table_label, field_hint)
		)


def qc_party_name(doc) -> str:
	if is_farmer_or_agent_qc(doc):
		return (doc.farmer_name or "").strip()
	return (doc.staff_name or "").strip()


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
