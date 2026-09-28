import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class RSTDetails(Document):
	def validate(self):
		self._validate_unique_rst_no()
		self.tp_status = "TP Pending Agent" if not (self.tp_no or "").strip() else "TP Received"

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
		transit_pass = _get_matching_transit_pass(self) if (self.tp_no or "").strip() else None

		values = {
			"demo_rst_data": self.name,
			"rst_no": self.rst_no,
			"same_truck_as_transit_pass": 1,
			"actual_truck_no": self.vehicle_no,
			"load_weight": flt(self.gross_vehicle_weight_qt),
			"tare_weight": flt(self.tare_vehicle_weight_qt),
			"deduction": flt(self.deduction_qt),
			"gunny_type": "Gunny Cut" if flt(self.gunny_weight_qt) > 0 else "Gunny Gross",
			"gunny_weight": flt(self.gunny_weight_qt),
			"commodity": self.commodity,
			"measurement_date": self.entry_date,
			"measurement_time": self.entry_time,
		}
		# Transit Pass fields are fetched from the unique key on WBM. Keep them
		# empty until an agent supplies a TP No on this RST record.
		if transit_pass:
			values["pass_unique_key"] = transit_pass.pass_unique_key

		if self.weigh_bridge_measurement and frappe.db.exists(
			"Weigh Bridge Measurement", self.weigh_bridge_measurement
		):
			wbm = frappe.get_doc("Weigh Bridge Measurement", self.weigh_bridge_measurement)
			for fieldname, value in values.items():
				wbm.set(fieldname, value)
			wbm.save(ignore_permissions=True)
		else:
			wbm = frappe.get_doc({"doctype": "Weigh Bridge Measurement", **values})
			wbm.insert(ignore_permissions=True)
			self.weigh_bridge_measurement = wbm.name
			self.db_set("weigh_bridge_measurement", wbm.name, update_modified=False)


def _get_matching_transit_pass(doc):
	tp_no = (doc.tp_no or "").strip()
	mill_no = (doc.mill_name or "").strip()
	ppc_name = (doc.ppc_name or "").strip()
	if not tp_no:
		return None
	if not (mill_no and ppc_name):
		frappe.throw(
			_("Enter TP No, Mill No, and PPC Name to find the matching transit pass.")
		)

	transit_passes = frappe.get_all(
		"PPAS Transit Pass",
		filters={"transit_pass_no": tp_no},
		fields=["pass_unique_key", "miller", "ppc"],
		order_by="pass_unique_key asc",
		limit_page_length=1000,
	)
	transit_passes = [
		row
		for row in transit_passes
		if _matches_mill_no(mill_no, row.miller, row.pass_unique_key)
		and _matches_name_or_code(ppc_name, row.ppc)
	]
	if not transit_passes:
		frappe.throw(_("No transit pass matches the TP No, Mill No, and PPC Name entered."))
	if len(transit_passes) > 1:
		frappe.throw(
			_("More than one transit pass matches these values. Make TP No, Mill No, and PPC Name more specific.")
		)
	return transit_passes[0]


def _matches_name_or_code(search_value, stored_value):
	search_value = (search_value or "").strip().casefold()
	stored_value = (stored_value or "").strip().casefold()
	if not search_value or not stored_value:
		return False
	if search_value == stored_value:
		return True
	name, separator, code = stored_value.partition("(")
	if separator:
		code = code.rstrip(") ").strip()
		return search_value in {name.strip(), code}
	return False


def _matches_mill_no(search_value, stored_miller, pass_unique_key):
	search_value = (search_value or "").strip().casefold()
	if _matches_name_or_code(search_value, stored_miller):
		return True
	key_mill_code = (pass_unique_key or "").partition("-")[0].strip().casefold()
	return bool(search_value and search_value == key_mill_code)
