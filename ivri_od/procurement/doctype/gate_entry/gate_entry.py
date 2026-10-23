# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, format_datetime, get_datetime, now_datetime

from ivri_od.procurement.datetime_fields import ensure_doc_datetime
from ivri_od.procurement.mill_gate import (
	get_open_gate_entry_in_for_vehicle,
	get_vehicles_inside_mill,
	is_gate_in_inside_mill,
	normalize_vehicle_no,
)
from ivri_od.procurement.pass_print import (
	qr_content_gate_entry,
	qr_image_html,
	render_template_file,
	send_pdf_download,
)

GATE_ENTRY_PARTY_NAME_FIELDS = ("party_name", "custom_party_name")


def _party_name_from_record(data) -> str:
	if not data:
		return ""
	getter = data.get if isinstance(data, dict) else lambda key, default=None: data.get(key, default)
	for fieldname in GATE_ENTRY_PARTY_NAME_FIELDS:
		value = (getter(fieldname) or "").strip()
		if value:
			return value
	return ""


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
		ensure_doc_datetime(
			self,
			"entry_datetime",
			default_now=True,
			date_field="entry_date",
			time_field="entry_time",
		)

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
		self._sync_party_name_fields()

	def _sync_party_name_fields(self):
		party = (self.get("party_name") or "").strip()
		custom = (self.get("custom_party_name") or "").strip()
		if custom and not party:
			self.party_name = custom
		elif party and not custom and self.meta.has_field("custom_party_name"):
			self.custom_party_name = party
		elif party:
			self.party_name = party

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


def party_name_for_gate_entry(gate_entry_name: str, doc=None) -> str:
	"""Party name on Gate Entry, else from the latest linked Quality Check."""
	name = (gate_entry_name or "").strip()
	if not name:
		return ""

	on_doc = _party_name_from_record(doc)
	if on_doc:
		return on_doc

	for fieldname in GATE_ENTRY_PARTY_NAME_FIELDS:
		stored = frappe.db.get_value("Gate Entry", name, fieldname)
		if (stored or "").strip():
			return stored.strip()

	qc_rows = frappe.get_all(
		"Quality Check",
		filters={"gate_entry": name},
		fields=["is_farmer_or_agent", "farmer_name", "staff_name"],
		order_by="modified desc",
		limit=1,
	)
	if not qc_rows:
		return ""
	qc = qc_rows[0]
	if cint(qc.is_farmer_or_agent):
		return (qc.farmer_name or "").strip()
	return (qc.staff_name or "").strip()


def _render_gate_entry_pass_html(doc, for_pdf: bool = False) -> str:
	entry_dt = doc.entry_datetime
	entry_datetime_display = format_datetime(entry_dt) if entry_dt else "—"
	party_name = party_name_for_gate_entry(doc.name, doc=doc)
	qr_text = qr_content_gate_entry(doc, entry_datetime_display, party_name=party_name)
	return render_template_file(
		("procurement", "doctype", "gate_entry", "gate_entry_pass.html"),
		{
			"doc": doc,
			"entry_datetime_display": entry_datetime_display,
			"party_name": party_name,
			"qr_image": qr_image_html(qr_text, module_px=4),
			"qr_text": qr_text,
			"for_pdf": for_pdf,
		},
	)


@frappe.whitelist()
def get_gate_entry_pass_html(name: str) -> str:
	doc = frappe.get_doc("Gate Entry", name)
	doc.check_permission("print")
	return _render_gate_entry_pass_html(doc)


@frappe.whitelist()
def download_gate_entry_pass_pdf(name: str):
	doc = frappe.get_doc("Gate Entry", name)
	doc.check_permission("print")
	html = _render_gate_entry_pass_html(doc, for_pdf=True)
	send_pdf_download(html, f"{doc.name}-gate-pass.pdf")


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
