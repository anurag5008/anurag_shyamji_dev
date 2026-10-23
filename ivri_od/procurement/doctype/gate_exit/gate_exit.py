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


class GateExit(Document):
	def validate(self):
		self.vehicle_no = normalize_vehicle_no(self.vehicle_no)
		if not self.vehicle_no:
			frappe.throw(_("Select Vehicle No for Gate Exit."))

		self.gate_entry_in = (self.gate_entry_in or "").strip() or get_open_gate_entry_in_for_vehicle(
			self.vehicle_no
		)
		if not self.gate_entry_in:
			frappe.throw(
				_("Vehicle {0} is not inside the mill. No open Gate In found.").format(
					frappe.bold(self.vehicle_no)
				),
				title=_("Vehicle Not Inside"),
			)

		gate_in = frappe.db.get_value(
			"Gate Entry", self.gate_entry_in, ["vehicle_no", "driver_name"], as_dict=True
		)
		if not gate_in or normalize_vehicle_no(gate_in.vehicle_no) != self.vehicle_no:
			frappe.throw(_("Selected Gate In does not match Vehicle No {0}.").format(self.vehicle_no))
		if not is_gate_in_inside_mill(self.gate_entry_in):
			frappe.throw(_("This Gate In already has a Gate Exit."))

		duplicate = frappe.db.exists(
			"Gate Exit",
			{"gate_entry_in": self.gate_entry_in, "name": ["!=", self.name]},
		)
		if duplicate:
			frappe.throw(_("Gate Exit already recorded for this visit ({0}).").format(duplicate))

		if not (self.driver_name or "").strip():
			self.driver_name = (gate_in.driver_name or "").strip()
		if not self.exit_datetime:
			self.exit_datetime = now_datetime()
		else:
			self.exit_datetime = get_datetime(self.exit_datetime)

	def on_update(self):
		frappe.db.set_value(
			"Gate Entry", self.gate_entry_in, "inside_mill", 0, update_modified=False
		)
		self._create_grn_notes()

	def _create_grn_notes(self):
		# GRN is generated when the vehicle leaves the mill, not at tare weight.
		from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
			create_grn_notes_after_gate_exit,
		)

		created = create_grn_notes_after_gate_exit(self.gate_entry_in)
		if created:
			frappe.msgprint(
				_("GRN Note created: {0}").format(", ".join(frappe.bold(name) for name in created)),
				indicator="green",
				alert=True,
			)

	def on_trash(self):
		if not self.gate_entry_in:
			return
		other_exit = frappe.db.exists(
			"Gate Exit",
			{"gate_entry_in": self.gate_entry_in, "name": ["!=", self.name]},
		)
		legacy_exit = frappe.db.exists(
			"Gate Entry",
			{"in_out": "Out", "gate_entry_in": self.gate_entry_in},
		)
		if not other_exit and not legacy_exit:
			frappe.db.set_value(
				"Gate Entry", self.gate_entry_in, "inside_mill", 1, update_modified=False
			)


@frappe.whitelist()
def get_inside_mill_vehicle_autocomplete(txt="", limit=25):
	vehicles = get_vehicles_inside_mill(txt=txt, limit=limit)
	return [{"value": vehicle, "label": vehicle, "description": ""} for vehicle in vehicles]


@frappe.whitelist()
def resolve_gate_exit_for_vehicle(vehicle_no):
	vehicle_no = normalize_vehicle_no(vehicle_no)
	gate_entry_in = get_open_gate_entry_in_for_vehicle(vehicle_no) if vehicle_no else None
	if not gate_entry_in:
		return {"error": _("Vehicle {0} is not inside the mill.").format(frappe.bold(vehicle_no))}
	gate_in = frappe.db.get_value(
		"Gate Entry", gate_entry_in, ["vehicle_no", "driver_name"], as_dict=True
	)
	return {
		"gate_entry_in": gate_entry_in,
		"vehicle_no": normalize_vehicle_no(gate_in.vehicle_no),
		"driver_name": (gate_in.driver_name or "").strip(),
	}
