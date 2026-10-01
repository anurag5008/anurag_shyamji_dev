import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ivri_od.procurement.mill_gate import normalize_vehicle_no
from ivri_od.procurement.transit_pass_resolve import (
	find_transit_passes_by_tp_and_ppc,
	get_agent_for_ppc_text,
	mill_id_from_transit_pass,
	party_name_exists_on_transit_pass,
)


class RSTDetails(Document):
	def validate(self):
		self._validate_unique_rst_no()
		self._sync_mill_and_agent_from_transit_pass()
		self._validate_mill_name()
		self._set_tp_status()

	def on_trash(self):
		wbm_name = self.weigh_bridge_measurement
		if wbm_name and frappe.db.exists("Weigh Bridge Measurement", wbm_name):
			frappe.delete_doc("Weigh Bridge Measurement", wbm_name, ignore_permissions=True)

	def on_update(self):
		try:
			self._sync_weigh_bridge_measurement()
		except Exception as exc:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"RST Details {self.name}: Weigh Bridge Measurement sync failed",
			)
			frappe.msgprint(
				_("RST Details was saved, but no Weigh Bridge Measurement was created: {0}").format(str(exc)),
				title=_("Transit Pass / Weigh Bridge Error"),
				indicator="red",
				alert=True,
			)

	def _sync_mill_and_agent_from_transit_pass(self):
		tp_no = (self.tp_no or "").strip()
		party_name = (self.party_name or "").strip()
		# Party is already a transit-pass PPC, but TP No is not on this RST yet.
		# Leave mill number alone. It is fetched when TP No is updated later.
		if party_found_awaiting_tp(self):
			return

		matches: list[dict] = []
		if tp_no and party_name and party_name_exists_on_transit_pass(party_name):
			matches = find_transit_passes_by_tp_and_ppc(tp_no, party_name)
			if len(matches) > 1:
				frappe.throw(
					_(
						"More than one transit pass matches TP No and Party Name. Contact support or refine Party Name."
					)
				)
			if len(matches) == 1:
				mill_id = mill_id_from_transit_pass(matches[0])
				if mill_id:
					self.mill_name = mill_id

		if is_private_procurement_rst(self):
			self.agent_name = ""
			return

		if len(matches) != 1:
			return

		agent = get_agent_for_ppc_text(party_name, matches[0].get("ppc"))
		if agent:
			self.agent_name = agent

	def _validate_mill_name(self):
		# Mill No is fetched only when Party Name and TP No are both present.
		if not (self.tp_no or "").strip():
			return
		if not (self.mill_name or "").strip() and party_name_exists_on_transit_pass(self.party_name):
			frappe.throw(
				_("Mill No could not be fetched from Transit Pass for this Party Name and TP No."),
				title=_("Missing Mill No"),
			)

	def _set_tp_status(self):
		if is_private_procurement_rst(self):
			self.tp_status = "Local Procurement"
		elif not (self.tp_no or "").strip():
			self.tp_status = "TP Pending Agent"
		else:
			self.tp_status = "TP Received"

	def _validate_unique_rst_no(self):
		rst_no = (self.rst_no or "").strip()
		if not rst_no:
			return

		filters = {"rst_no": rst_no}
		if not self.is_new():
			filters["name"] = ["!=", self.name]

		if frappe.db.exists("RST Details", filters):
			frappe.throw(
				_("RST No {0} already exists. Enter a unique RST No.").format(frappe.bold(rst_no)),
				title=_("Duplicate RST No"),
			)

	def _sync_weigh_bridge_measurement(self):
		private = is_private_procurement_rst(self)
		awaiting_tp = party_found_awaiting_tp(self)
		transit_pass = None
		if not private and not awaiting_tp:
			transit_pass = try_get_matching_transit_pass(self)
			if not transit_pass:
				return

		values = {
			"demo_rst_data": self.name,
			"rst_no": self.rst_no,
			"load_weight": flt(self.gross_vehicle_weight_qt),
			"tare_weight": flt(self.tare_vehicle_weight_qt),
			"deduction": flt(self.deduction_qt),
			"gunny_type": "Gunny Cut" if flt(self.gunny_weight_qt) > 0 else "Gunny Gross",
			"gunny_weight": flt(self.gunny_weight_qt),
			"commodity": self.commodity,
			"measurement_date": self.entry_date,
			"measurement_time": self.entry_time,
		}

		if private:
			values.update(
				{
					"is_farmer_or_agent": 1,
					"vehicle_no": "",
					"same_truck_as_transit_pass": 0,
					"actual_truck_no": normalize_vehicle_no(self.vehicle_no),
					"pass_unique_key": "",
					"agent_name": "",
				}
			)
		elif awaiting_tp:
			# Party is a known PPC and TP No is still empty. Create the weigh bridge
			# without a mill number or transit pass. RST vehicle goes to Actual Truck No.
			# Mill is fetched when TP No is updated.
			rst_vehicle = (self.vehicle_no or "").strip().upper()
			values.update(
				{
					"is_farmer_or_agent": 0,
					"agent_name": "",
					"same_truck_as_transit_pass": 1 if rst_vehicle else 0,
					"actual_truck_no": rst_vehicle,
					"pass_unique_key": "",
					"vehicle_no": "",
				}
			)
		else:
			values.update(
				{
					"is_farmer_or_agent": 0,
					"agent_name": self.agent_name,
					"same_truck_as_transit_pass": 1,
					"actual_truck_no": (self.vehicle_no or "").strip().upper(),
					"pass_unique_key": transit_pass.pass_unique_key,
					"vehicle_no": "",
				}
			)

		if self.weigh_bridge_measurement and frappe.db.exists(
			"Weigh Bridge Measurement", self.weigh_bridge_measurement
		):
			wbm = frappe.get_doc("Weigh Bridge Measurement", self.weigh_bridge_measurement)
			for fieldname, value in values.items():
				wbm.set(fieldname, value)
			if awaiting_tp:
				wbm.flags.ignore_mandatory = True
			wbm.save(ignore_permissions=True)
		else:
			wbm = frappe.get_doc({"doctype": "Weigh Bridge Measurement", **values})
			if awaiting_tp:
				wbm.flags.ignore_mandatory = True
			wbm.insert(ignore_permissions=True)
			self.weigh_bridge_measurement = wbm.name
			self.db_set("weigh_bridge_measurement", wbm.name, update_modified=False)


def party_found_awaiting_tp(doc) -> bool:
	"""Party Name is a transit-pass PPC and this RST has no TP No yet."""
	tp_no = (getattr(doc, "tp_no", None) or "").strip()
	party_name = (getattr(doc, "party_name", None) or getattr(doc, "ppc_name", None) or "").strip()
	if tp_no or not party_name:
		return False
	return party_name_exists_on_transit_pass(party_name)


def is_private_procurement_rst(doc) -> bool:
	"""Farmer/agent only when Party Name is not a transit-pass PPC and TP No is empty."""
	tp_no = (getattr(doc, "tp_no", None) or "").strip()
	party_name = (getattr(doc, "party_name", None) or getattr(doc, "ppc_name", None) or "").strip()
	if tp_no or not party_name:
		return False
	return not party_name_exists_on_transit_pass(party_name)


def is_local_procurement_rst(doc) -> bool:
	return is_private_procurement_rst(doc)


def get_rst_agent_name(demo_rst_data=None, rst_no=None) -> str | None:
	"""Agent from RST only when the party is a transit-pass PPC. Local procurement has no agent."""
	rst_name = (demo_rst_data or "").strip()
	if not rst_name and (rst_no or "").strip():
		rst_name = frappe.db.get_value("RST Details", {"rst_no": (rst_no or "").strip()}, "name")
	if not rst_name or not frappe.db.exists("RST Details", rst_name):
		return None
	rst = frappe.db.get_value(
		"RST Details",
		rst_name,
		["agent_name", "party_name", "tp_no"],
		as_dict=True,
	)
	if not rst:
		return None
	doc = frappe._dict(tp_no=rst.tp_no, party_name=rst.party_name)
	if is_private_procurement_rst(doc):
		return None
	return (rst.agent_name or "").strip() or None


def try_get_matching_transit_pass(doc):
	tp_no = (doc.tp_no or "").strip()
	party_name = (getattr(doc, "party_name", None) or getattr(doc, "ppc_name", None) or "").strip()
	if not tp_no or not party_name:
		return None

	transit_passes = find_transit_passes_by_tp_and_ppc(tp_no, party_name)
	if not transit_passes:
		return None
	if len(transit_passes) > 1:
		frappe.throw(
			_("More than one transit pass matches TP No and Party Name. Make Party Name more specific.")
		)
	return frappe._dict(transit_passes[0])


@frappe.whitelist()
def check_private_procurement(tp_no=None, party_name=None):
	doc = frappe._dict(tp_no=(tp_no or "").strip(), party_name=(party_name or "").strip())
	return {"is_private": is_private_procurement_rst(doc)}


@frappe.whitelist()
def fetch_mill_and_agent_from_tp(tp_no=None, party_name=None, ppc_name=None):
	"""Backward compatible API (ppc_name alias for party_name)."""
	party_name = (party_name or ppc_name or "").strip()
	tp_no = (tp_no or "").strip()
	if not tp_no or not party_name or not party_name_exists_on_transit_pass(party_name):
		return {"mill_name": "", "agent_name": ""}

	matches = find_transit_passes_by_tp_and_ppc(tp_no, party_name)
	if not matches:
		return {
			"mill_name": "",
			"agent_name": get_agent_for_ppc_text(party_name) or "",
		}
	if len(matches) > 1:
		return {
			"error": _("More than one transit pass matches TP No and Party Name."),
		}

	row = matches[0]
	return {
		"mill_name": mill_id_from_transit_pass(row),
		"agent_name": get_agent_for_ppc_text(party_name, row.ppc) or "",
	}
