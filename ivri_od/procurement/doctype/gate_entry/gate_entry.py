# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from ivri_od.procurement.mill_gate import (
	get_open_gate_entry_in_for_vehicle,
	get_vehicles_inside_mill,
	is_gate_in_inside_mill,
	normalize_vehicle_no,
)


class GateEntry(Document):
	def validate(self):
		if self.is_new() and not self.in_out:
			self.in_out = "In"
		self._normalize_fields()
		self._clear_fields_by_movement()
		self._sync_gate_in_datetime()
		self._sync_weighment_flag()
		self._sync_inside_mill_flag()
		self._validate_purpose_details()
		self._validate_mill_visit()
		self._validate_closed_gate_in_unchanged()

	def _sync_gate_in_datetime(self):
		if self.in_out != "In":
			return
		if self.entry_datetime:
			value = get_datetime(self.entry_datetime)
		elif self.entry_date and self.entry_time:
			value = get_datetime(f"{self.entry_date} {self.entry_time}")
		else:
			value = now_datetime()
		self.entry_datetime = value
		self.entry_date = value.date()
		self.entry_time = value.time().replace(microsecond=0)

	def _sync_weighment_flag(self):
		if self.in_out != "In":
			return
		if self.in_purpose in ("Paddy", "Rice"):
			self.going_to_weighment = 1
		elif self.in_purpose == "Others":
			self.going_to_weighment = 1 if self.going_to_weighment else 0
		else:
			self.going_to_weighment = 0

	def on_update(self):
		self._close_gate_in_on_gate_out()

	def on_trash(self):
		self._reopen_gate_in_on_gate_out_delete()

	def _sync_inside_mill_flag(self):
		if self.in_out == "In":
			if self.is_new():
				self.inside_mill = 1
			else:
				self.inside_mill = 1 if is_gate_in_inside_mill(self.name) else 0
		else:
			self.inside_mill = 0

	def _close_gate_in_on_gate_out(self):
		if self.in_out != "Out" or not (self.gate_entry_in or "").strip():
			return
		frappe.db.set_value(
			"Gate Entry",
			self.gate_entry_in,
			"inside_mill",
			0,
			update_modified=False,
		)

	def _reopen_gate_in_on_gate_out_delete(self):
		if self.in_out != "Out" or not (self.gate_entry_in or "").strip():
			return
		other_out = frappe.db.exists(
			"Gate Entry",
			{
				"in_out": "Out",
				"gate_entry_in": self.gate_entry_in,
				"name": ["!=", self.name],
			},
		)
		if other_out:
			return
		frappe.db.set_value(
			"Gate Entry",
			self.gate_entry_in,
			"inside_mill",
			1,
			update_modified=False,
		)

	def _normalize_fields(self):
		if self.vehicle_no:
			self.vehicle_no = normalize_vehicle_no(self.vehicle_no)
		if self.driver_name:
			self.driver_name = self.driver_name.strip()
		if self.gate_entry_in:
			self.gate_entry_in = self.gate_entry_in.strip()

	def _clear_fields_by_movement(self):
		if self.in_out == "In":
			self.out_purpose = ""
			self.out_purpose_detail = ""
			self.gate_entry_in = ""
			if self.in_purpose != "Others":
				self.purpose = ""
		elif self.in_out == "Out":
			self.in_purpose = ""
			self.purpose = ""
			self.going_to_weighment = 0
			if self.out_purpose != "Others":
				self.out_purpose_detail = ""
		else:
			self.in_purpose = ""
			self.purpose = ""
			self.out_purpose = ""
			self.out_purpose_detail = ""
			self.going_to_weighment = 0
			self.gate_entry_in = ""

	def _validate_mill_visit(self):
		if self.in_out == "In":
			self._validate_gate_in()
		elif self.in_out == "Out":
			self._validate_gate_out()

	def _validate_purpose_details(self):
		if self.in_out == "In":
			if not (self.in_purpose or "").strip():
				frappe.throw(_("Select a purpose for Gate In."))
			if self.in_purpose == "Others" and not (self.purpose or "").strip():
				frappe.throw(_("Enter Purpose Details when Gate In purpose is Others."))
		elif self.in_out == "Out":
			if not (self.out_purpose or "").strip():
				frappe.throw(_("Select a purpose for Gate Out."))
			if self.out_purpose == "Others" and not (self.out_purpose_detail or "").strip():
				frappe.throw(_("Enter Purpose Details when Gate Out purpose is Others."))

	def _validate_closed_gate_in_unchanged(self):
		if self.is_new() or self.in_out != "In":
			return
		if not frappe.db.exists(
			"Gate Entry", {"in_out": "Out", "gate_entry_in": self.name}
		):
			return

		previous = self.get_doc_before_save()
		if not previous:
			return
		fields = ("vehicle_no", "in_purpose", "purpose", "entry_datetime")
		if any((self.get(fieldname) or "") != (previous.get(fieldname) or "") for fieldname in fields):
			frappe.throw(
				_("Vehicle, purpose, and Gate In time cannot be changed after Gate Out is recorded."),
				title=_("Gate Visit Closed"),
			)

	def _validate_gate_in(self):
		if not self.vehicle_no:
			frappe.throw(_("Select Vehicle No for Gate In."))

		open_visit = get_open_gate_entry_in_for_vehicle(self.vehicle_no, exclude_in=self.name)
		if open_visit:
			frappe.throw(
				_(
					"Vehicle {0} is already inside the mill (Gate In {1}). Record Gate Out before a new Gate In."
				).format(frappe.bold(self.vehicle_no), frappe.bold(open_visit)),
				title=_("Vehicle Already Inside"),
			)

	def _validate_gate_out(self):
		if not self.vehicle_no:
			frappe.throw(_("Select Vehicle No for Gate Out."))

		if not self.gate_entry_in:
			self.gate_entry_in = get_open_gate_entry_in_for_vehicle(self.vehicle_no) or ""

		if not self.gate_entry_in:
			frappe.throw(
				_("Vehicle {0} is not inside the mill. No open Gate In found.").format(
					frappe.bold(self.vehicle_no)
				),
				title=_("Vehicle Not Inside"),
			)

		gate_in = frappe.db.get_value(
			"Gate Entry",
			self.gate_entry_in,
			["in_out", "vehicle_no"],
			as_dict=True,
		)
		if not gate_in or gate_in.in_out != "In":
			frappe.throw(_("Gate Entry In {0} is invalid.").format(frappe.bold(self.gate_entry_in)))

		in_vehicle = normalize_vehicle_no(gate_in.vehicle_no)
		if in_vehicle != self.vehicle_no:
			frappe.throw(
				_("Vehicle {0} does not match Gate In record ({1}).").format(
					frappe.bold(self.vehicle_no),
					frappe.bold(in_vehicle),
				)
			)

		if not is_gate_in_inside_mill(self.gate_entry_in):
			frappe.throw(
				_("Gate In {0} is already closed with a Gate Out.").format(
					frappe.bold(self.gate_entry_in)
				),
				title=_("Visit Already Closed"),
			)

		duplicate_out = frappe.db.get_value(
			"Gate Entry",
			{"in_out": "Out", "gate_entry_in": self.gate_entry_in},
			"name",
		)
		if duplicate_out and duplicate_out != self.name:
			frappe.throw(
				_("Gate Out already recorded for this visit ({0}).").format(frappe.bold(duplicate_out))
			)


@frappe.whitelist()
def get_inside_mill_vehicle_autocomplete(txt="", limit=25):
	vehicles = get_vehicles_inside_mill(txt=txt, limit=limit)
	return [{"value": v, "label": v, "description": ""} for v in vehicles]


@frappe.whitelist()
def resolve_gate_out_for_vehicle(vehicle_no):
	vehicle_no = normalize_vehicle_no(vehicle_no)
	if not vehicle_no:
		return {"error": _("Enter Vehicle No.")}

	gate_entry_in = get_open_gate_entry_in_for_vehicle(vehicle_no)
	if not gate_entry_in:
		return {
			"error": _("Vehicle {0} is not inside the mill.").format(frappe.bold(vehicle_no))
		}

	ge = frappe.db.get_value(
		"Gate Entry",
		gate_entry_in,
		["driver_name", "vehicle_no"],
		as_dict=True,
	)
	return {
		"gate_entry_in": gate_entry_in,
		"vehicle_no": normalize_vehicle_no(ge.vehicle_no) if ge else vehicle_no,
		"driver_name": (ge.driver_name or "").strip() if ge else "",
	}
