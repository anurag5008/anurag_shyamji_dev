# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt, format_datetime, format_time, formatdate, get_datetime, get_time, getdate, nowdate, nowtime

from ivri_od.procurement.datetime_fields import combine_datetime, ensure_doc_datetime
from ivri_od.procurement.doctype.rst_details.rst_details import get_rst_agent_name
from ivri_od.procurement.doctype.weigh_bridge_measurement.weigh_bridge_measurement import (
	is_local_procurement_wbm,
)
from ivri_od.procurement.doctype.season_mapping.season_mapping import get_chhatni_from_season_mapping
from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
from ivri_od.procurement.mill_gate import get_qc_sl_no, normalize_vehicle_no
from ivri_od.procurement.grn_tp_fulfillment import (
	chhatni_fulfillment_status,
	clear_tp_fulfillment_fields,
	refresh_tp_fulfillment_for_pass,
)
from ivri_od.procurement.pass_print import (
	qr_content_grn_note,
	qr_image_html,
	render_template_file,
	send_pdf_download,
)
from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name, resolve_ppc_master_name

_TP_SYNC_FIELDS = [
	"season",
	"transit_pass_no",
	"transit_pass_date",
	"transit_pass_time",
	"quantity",
	"pacs",
	"ppc",
	"miller",
]


def _datetime_from_date_and_time(date_val, time_val):
	if not date_val:
		return None
	if time_val:
		return get_datetime(f"{date_val} {time_val}")
	return get_datetime(f"{date_val} 00:00:00")


def _transit_pass_datetime_from_row(tp) -> object | None:
	if not tp:
		return None
	date_val = tp.get("transit_pass_date") if isinstance(tp, dict) else tp.transit_pass_date
	time_val = tp.get("transit_pass_time") if isinstance(tp, dict) else tp.transit_pass_time
	return _datetime_from_date_and_time(date_val, time_val)


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
		receipt_dt = combine_datetime(
			self, "receipt_datetime", "receipt_date", "receipt_time"
		)
		year = getdate(receipt_dt or nowdate()).year
		self.name = make_autoname(f"GRN-{year}-.#####", doc=self)

	def before_insert(self):
		self._assign_grn_no()

	def validate(self):
		self._sync_datetime_fields()
		self._ensure_grn_no()
		self._normalize_fields()
		self._sync_local_procurement_flags()
		self._validate_farmer_or_agent_agent()
		if cint(self.is_local_procurement):
			self._validate_and_sync_rst()
			self._sync_local_procurement_from_rst()
			self._sync_ppc_name_from_quality_check()
		else:
			self._validate_pass_unique_key()
			self._sync_from_transit_pass()
			self._sync_entry_details_from_pass()
			self._validate_and_sync_rst()
			self._sync_ppc_name_from_quality_check()
		if self.is_new():
			self._sync_chhatni_from_season_mapping()
		self._sync_tp_fulfillment_status()
		self._set_purchase_heading()

	def on_update(self):
		self._schedule_procurement_rollup_sync()

	def _schedule_procurement_rollup_sync(self):
		key = (self.pass_unique_key or "").strip()
		if not key or cint(self.is_local_procurement):
			return
		frappe.db.after_commit(lambda k=key: _sync_procurement_rollups_for_pass(k))

	def on_trash(self):
		key = (self.pass_unique_key or "").strip()
		if key and not cint(self.is_local_procurement):
			frappe.db.after_commit(lambda k=key: refresh_tp_fulfillment_for_pass(k))
			frappe.db.after_commit(lambda k=key: _sync_procurement_rollups_for_pass(k))

	def _sync_tp_fulfillment_status(self):
		if cint(self.is_local_procurement) or not (self.pass_unique_key or "").strip():
			clear_tp_fulfillment_fields(self)
			return
		key = (self.pass_unique_key or "").strip()
		refresh_tp_fulfillment_for_pass(key)
		if not self.name:
			return
		row = frappe.db.get_value(
			"GRN Note",
			self.name,
			[
				"received_quantity",
				"tp_cumulative_received",
				"tp_chhatni_balance",
				"tp_fulfillment_status",
				"chhatni_fulfillment_status",
				"chhatni_fulfillment_remark",
			],
			as_dict=True,
		)
		if row:
			self.received_quantity = flt(row.received_quantity)
			self.tp_cumulative_received = flt(row.tp_cumulative_received)
			self.tp_chhatni_balance = flt(row.tp_chhatni_balance)
			self.tp_fulfillment_status = row.tp_fulfillment_status or ""
			self.chhatni_fulfillment_status = row.chhatni_fulfillment_status or ""
			self.chhatni_fulfillment_remark = row.chhatni_fulfillment_remark or ""

	def _set_purchase_heading(self):
		if cint(self.is_local_procurement):
			self.local_procurement_note = _("Local Paddy Purchase")
		else:
			self.is_local_procurement = 0
			self.local_procurement_note = _("Government Paddy Purchase")

	def _sync_ppc_name_from_quality_check(self):
		qc_name = (self.quality_check or "").strip()
		if not qc_name or not frappe.db.exists("Quality Check", qc_name):
			self.qc_bag_details = []
			return

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

	def _sync_datetime_fields(self):
		ensure_doc_datetime(
			self,
			"receipt_datetime",
			default_now=True,
			date_field="receipt_date",
			time_field="receipt_time",
		)
		ensure_doc_datetime(
			self,
			"arrival_datetime",
			date_field="arrival_date",
			time_field="arrival_time",
		)
		ensure_doc_datetime(
			self,
			"gate_exit_datetime",
			date_field="gate_exit_date",
			time_field="gate_out_time",
		)

	def _normalize_fields(self):
		self.pass_unique_key = (self.pass_unique_key or "").strip()
		self.rst_no = (self.rst_no or "").strip()
		if self.paddy_variety:
			self.paddy_variety = self.paddy_variety.strip()

	def _validate_farmer_or_agent_agent(self):
		if not cint(self.is_farmer_or_agent) or cint(self.is_local_procurement):
			if cint(self.is_local_procurement):
				self.agent_name = ""
			return
		if not (self.agent_name or "").strip():
			wbm_name = (self.weigh_bridge_measurement or "").strip()
			rst_link = (
				frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "demo_rst_data")
				if wbm_name
				else None
			)
			agent = get_rst_agent_name(demo_rst_data=rst_link, rst_no=self.rst_no)
			if agent:
				self.agent_name = agent
		if not (self.agent_name or "").strip():
			frappe.throw(_("Select Agent Name for farmer / agent procurement."))

	def _sync_local_procurement_flags(self):
		if cint(self.is_local_procurement):
			self.local_procurement_note = _("Local Paddy Purchase")
			self.pass_unique_key = ""
			self.mill_name = ""
			return
		self.local_procurement_note = _("Government Paddy Purchase")
		wbm_name = (self.weigh_bridge_measurement or "").strip()
		if not wbm_name and (self.rst_no or "").strip():
			wbm_name = _resolve_wbm_for_rst(self.rst_no, self.pass_unique_key) or ""
		if wbm_name and is_local_procurement_wbm(wbm_name):
			self.is_local_procurement = 1
			self.is_farmer_or_agent = 1
			self.local_procurement_note = _("Local Paddy Purchase")
			self.pass_unique_key = ""

	def _sync_local_procurement_from_rst(self):
		if not cint(self.is_local_procurement):
			return
		wbm_name = (self.weigh_bridge_measurement or "").strip()
		if not wbm_name:
			return
		rst_link = frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "demo_rst_data")
		if not rst_link or not frappe.db.exists("RST Details", rst_link):
			return
		rst = frappe.db.get_value(
			"RST Details",
			rst_link,
			["party_name", "commodity", "entry_date", "entry_time", "agent_name"],
			as_dict=True,
		)
		if not rst:
			return
		if not (self.ppc_name or "").strip():
			self.ppc_name = (rst.party_name or "").strip()
		self.agent_name = ""
		self.is_farmer_or_agent = 1
		if not (self.paddy_variety or "").strip() and (rst.commodity or "").strip():
			self.paddy_variety = rst.commodity.strip()
		if not self.receipt_datetime and rst.entry_date:
			self.receipt_date = rst.entry_date
			self.receipt_time = rst.entry_time or nowtime()
			ensure_doc_datetime(
				self,
				"receipt_datetime",
				date_field="receipt_date",
				time_field="receipt_time",
			)

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
			_TP_SYNC_FIELDS,
			as_dict=True,
		)
		if not tp:
			self.mill_name = ""
			return

		self.cmr_season = (tp.season or "").strip()
		self.transit_pass_no = tp.transit_pass_no
		self.transit_pass_date = tp.transit_pass_date
		self.transit_pass_datetime = _transit_pass_datetime_from_row(tp)
		self.tp_quantity = flt(tp.quantity)
		self.pacs = (tp.pacs or "").strip()
		self.ppc = (tp.ppc or "").strip()
		self.mill_name = (tp.miller or "").strip()

	def _mill_master_link_for_grn(self) -> str:
		if cint(self.is_local_procurement):
			return ""
		return resolve_mill_master_name(self.pass_unique_key, self.mill_name) or ""

	def _sync_chhatni_from_season_mapping(self):
		mill_link = self._mill_master_link_for_grn()
		ppc_link = resolve_ppc_master_name(self.ppc) or resolve_ppc_master_name(self.ppc_name)
		season_link = resolve_season_master_name(self.cmr_season)
		if not (mill_link and ppc_link and season_link):
			self.chhatni = 0
			return
		self.chhatni = get_chhatni_from_season_mapping(season_link, ppc_link, mill_link)

	def _validate_and_sync_rst(self):
		rst_no = (self.rst_no or "").strip()
		if not rst_no:
			frappe.throw(_("Enter RST No from Weigh Bridge Measurement."))

		pass_key = (self.pass_unique_key or "").strip() if not cint(self.is_local_procurement) else ""
		wbm_name = _resolve_wbm_for_rst(rst_no, pass_key or None)
		if not wbm_name:
			frappe.throw(
				_("No Weigh Bridge Measurement found for RST No {0}.").format(frappe.bold(rst_no))
			)

		self.weigh_bridge_measurement = wbm_name
		if cint(self.is_local_procurement) or is_local_procurement_wbm(wbm_name):
			self.is_local_procurement = 1
		strict_wbm = (
			not cint(self.is_local_procurement) and not getattr(self.flags, "auto_from_wbm", False)
		)
		self._apply_weigh_bridge(wbm_name, strict=strict_wbm)
		qc_name = (self.quality_check or "").strip()
		if qc_name:
			self._apply_quality_check(qc_name)
		self._apply_gate_entry((self.gate_entry or "").strip())

	def _apply_weigh_bridge(self, wbm_name: str, strict: bool = True):
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
				"deduction",
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
				"agent_name",
			],
			as_dict=True,
		)
		if not wbm:
			return
		if strict:
			if wbm.quality_test not in ("Accepted", "Partially Accepted"):
				frappe.throw(
					_("GRN Note can be created only when Quality Test is Accepted or Partially Accepted.")
				)
			if not flt(wbm.tare_weight):
				frappe.throw(_("GRN Note can be created only when tare weight is greater than zero."))

		if not cint(self.is_local_procurement):
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
		self.deduction = flt(wbm.deduction)
		self.gunny_type = wbm.gunny_type or ""
		self.gunny_weight = flt(wbm.gunny_weight)
		self.gate_entry = (wbm.gate_entry or "").strip()
		self.quality_check = (wbm.quality_check or "").strip()
		self.qc_sample_no = cint(wbm.slno_of_qc) or get_qc_sl_no(self.quality_check)
		if getattr(self.flags, "syncing_from_wbm", False) or cint(wbm.no_of_bags):
			self.no_of_bags = cint(wbm.no_of_bags)

		self.is_farmer_or_agent = cint(wbm.is_farmer_or_agent)
		if self.is_farmer_or_agent and not cint(self.is_local_procurement):
			self.agent_name = (wbm.agent_name or "").strip()
			if not self.agent_name:
				rst_link = frappe.db.get_value(
					"Weigh Bridge Measurement", wbm_name, "demo_rst_data"
				)
				self.agent_name = get_rst_agent_name(
					demo_rst_data=rst_link, rst_no=self.rst_no
				) or ""
			vehicle = (wbm.actual_truck_no or wbm.vehicle_no or "").strip()
		elif self.is_farmer_or_agent:
			self.agent_name = ""
			vehicle = (wbm.actual_truck_no or wbm.vehicle_no or "").strip()
		else:
			self.agent_name = ""
			vehicle = (wbm.actual_truck_no or wbm.truck_no_in_tp or "").strip()
		self.vehicle_no = normalize_vehicle_no(vehicle)
		self._apply_wbm_bag_details(wbm_name)

	def _apply_wbm_bag_details(self, wbm_name: str):
		jute, plastic, total = _wbm_bag_counts_from_child_table(wbm_name)
		self.jute_bags = jute
		self.plastic_bags = plastic
		self.total_bags = total

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
		self.party_name = ""
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
		self.gate_exit = ""
		self.gate_exit_datetime = None
		self.gate_exit_date = None
		self.gate_out_time = None
		self.arrival_datetime = None
		self.arrival_date = None
		self.arrival_time = None
		if not gate_entry or not frappe.db.exists("Gate Entry", gate_entry):
			return

		ge = frappe.db.get_value(
			"Gate Entry",
			gate_entry,
			["entry_datetime", "entry_date", "entry_time", "driver_name", "vehicle_no", "in_out"],
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
			["entry_datetime", "entry_date", "entry_time", "driver_name", "vehicle_no"],
			as_dict=True,
		)
		if gate_in_row:
			if gate_in_row.entry_datetime:
				self.arrival_datetime = get_datetime(gate_in_row.entry_datetime)
			else:
				self.arrival_date = gate_in_row.entry_date
				self.arrival_time = gate_in_row.entry_time
			ensure_doc_datetime(
				self,
				"arrival_datetime",
				date_field="arrival_date",
				time_field="arrival_time",
			)
			if not (self.driver_name or "").strip():
				self.driver_name = (gate_in_row.driver_name or "").strip()
			if not (self.vehicle_no or "").strip():
				self.vehicle_no = normalize_vehicle_no(gate_in_row.vehicle_no)

		exit_row = _latest_gate_exit(gate_in, self.vehicle_no or (gate_in_row.vehicle_no if gate_in_row else ""))
		if not exit_row or not exit_row.exit_datetime:
			return
		self.gate_exit = exit_row.name
		self.gate_exit_datetime = get_datetime(exit_row.exit_datetime)
		ensure_doc_datetime(
			self,
			"gate_exit_datetime",
			date_field="gate_exit_date",
			time_field="gate_out_time",
		)


def _latest_gate_exit(gate_in: str | None, vehicle_no: str | None):
	"""Gate Exit for this visit, then the latest exit for the same vehicle."""
	gate_in = (gate_in or "").strip()
	if gate_in:
		rows = frappe.get_all(
			"Gate Exit",
			filters={"gate_entry_in": gate_in},
			fields=["name", "exit_datetime"],
			order_by="exit_datetime desc",
			limit=1,
		)
		if rows:
			return rows[0]

	vehicle_no = normalize_vehicle_no(vehicle_no)
	if not vehicle_no:
		return None
	rows = frappe.get_all(
		"Gate Exit",
		filters={"vehicle_no": vehicle_no},
		fields=["name", "exit_datetime"],
		order_by="exit_datetime desc",
		limit=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def sync_gate_exit_on_grn(grn_name: str | None = None):
	"""Fill Gate Exit, date, and time on an open GRN when that vehicle has exited."""
	grn_name = (grn_name or "").strip()
	if not grn_name or not frappe.db.exists("GRN Note", grn_name):
		return {
			"gate_exit": "",
			"gate_exit_datetime": None,
			"gate_exit_date": None,
			"gate_out_time": None,
		}
	doc = frappe.get_doc("GRN Note", grn_name)
	doc._apply_gate_entry((doc.gate_entry or "").strip())
	doc.db_set(
		{
			"gate_exit": doc.gate_exit or "",
			"gate_exit_datetime": doc.gate_exit_datetime,
			"gate_exit_date": doc.gate_exit_date,
			"gate_out_time": doc.gate_out_time,
			"arrival_datetime": doc.arrival_datetime,
			"arrival_date": doc.arrival_date,
			"arrival_time": doc.arrival_time,
		},
		update_modified=False,
	)
	return {
		"gate_exit": doc.gate_exit or "",
		"gate_exit_datetime": doc.gate_exit_datetime,
		"gate_exit_date": doc.gate_exit_date,
		"gate_out_time": doc.gate_out_time,
		"arrival_datetime": doc.arrival_datetime,
	}


def sync_grn_from_weigh_bridge(wbm_name: str) -> str | None:
	"""Push WBM/QC/gate changes into linked GRN and recalculate TP fulfillment for the pass."""
	wbm_name = (wbm_name or "").strip()
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return None

	if getattr(frappe.local, "syncing_grn_from_wbm", None) == wbm_name:
		return None

	grn_name = frappe.db.get_value(
		"GRN Note",
		{"weigh_bridge_measurement": wbm_name, "docstatus": ["<", 2]},
		"name",
	)
	if not grn_name:
		return None

	frappe.local.syncing_grn_from_wbm = wbm_name
	try:
		grn = frappe.get_doc("GRN Note", grn_name)
		wbm = frappe.db.get_value(
			"Weigh Bridge Measurement",
			wbm_name,
			["rst_no", "pass_unique_key", "date", "measurement_date", "measurement_time", "commodity"],
			as_dict=True,
		)
		if not wbm:
			return grn_name

		if (wbm.rst_no or "").strip():
			grn.rst_no = (wbm.rst_no or "").strip()
		grn.weigh_bridge_measurement = wbm_name

		if is_local_procurement_wbm(wbm_name):
			grn.is_local_procurement = 1
			grn.pass_unique_key = ""
			grn._sync_local_procurement_from_rst()
			if wbm.date:
				grn.receipt_datetime = get_datetime(wbm.date)
			elif wbm.measurement_date:
				grn.receipt_date = wbm.measurement_date
				grn.receipt_time = wbm.measurement_time
			ensure_doc_datetime(
				grn,
				"receipt_datetime",
				date_field="receipt_date",
				time_field="receipt_time",
			)
			if (wbm.commodity or "").strip() and not (grn.paddy_variety or "").strip():
				grn.paddy_variety = wbm.commodity.strip()
		else:
			wbm_pass = (wbm.pass_unique_key or "").strip()
			if wbm_pass and wbm_pass != (grn.pass_unique_key or "").strip():
				grn.pass_unique_key = wbm_pass

		grn.flags.syncing_from_wbm = True
		grn.flags.auto_from_wbm = True
		grn._apply_weigh_bridge(wbm_name, strict=False)

		qc_name = (grn.quality_check or "").strip()
		if qc_name:
			grn._apply_quality_check(qc_name)
		grn._sync_ppc_name_from_quality_check()

		grn._apply_gate_entry((grn.gate_entry or "").strip())

		if not cint(grn.is_local_procurement):
			grn._sync_from_transit_pass()
			grn._sync_entry_details_from_pass()

		grn.flags.ignore_validate = True
		grn.save(ignore_permissions=True)

		if not cint(grn.is_local_procurement) and (grn.pass_unique_key or "").strip():
			pass_key = (grn.pass_unique_key or "").strip()
			refresh_tp_fulfillment_for_pass(pass_key)
			row = frappe.db.get_value(
				"GRN Note",
				grn_name,
				[
					"received_quantity",
					"tp_cumulative_received",
					"tp_chhatni_balance",
					"tp_fulfillment_status",
					"chhatni_fulfillment_status",
					"chhatni_fulfillment_remark",
				],
				as_dict=True,
			)
			if row:
				frappe.db.set_value("GRN Note", grn_name, row, update_modified=False)

		return grn_name
	finally:
		if getattr(frappe.local, "syncing_grn_from_wbm", None) == wbm_name:
			frappe.local.syncing_grn_from_wbm = None


def build_auto_grn_doc_dict(wbm_name: str) -> dict | None:
	"""Build a full GRN Note payload when a WBM is eligible (manual or RST-linked)."""
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return None
	if frappe.db.exists(
		"GRN Note",
		{"weigh_bridge_measurement": wbm_name, "docstatus": ["<", 2]},
	):
		return None

	if not flt(frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "tare_weight")):
		return None

	quality_test = frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "quality_test") or ""
	if quality_test not in ("Accepted", "Partially Accepted"):
		return None

	if is_local_procurement_wbm(wbm_name):
		return grn_dict_for_local_wbm(wbm_name)

	wbm = frappe.db.get_value(
		"Weigh Bridge Measurement",
		wbm_name,
		["quality_test", "pass_unique_key", "rst_no", "is_farmer_or_agent", "agent_name", "demo_rst_data"],
		as_dict=True,
	)
	if not wbm:
		return None
	rst_no = (wbm.rst_no or "").strip()
	pass_key = (wbm.pass_unique_key or "").strip()
	if not rst_no or not pass_key:
		return None

	qc_ok = (wbm.quality_test or "") in ("Accepted", "Partially Accepted")
	details = _grn_details_from_rst(rst_no, pass_key, strict_wbm=qc_ok)
	if details.get("error"):
		return None

	payload = {k: v for k, v in details.items() if k != "error"}
	payload.update(
		{
			"doctype": "GRN Note",
			"pass_unique_key": pass_key,
			"rst_no": rst_no,
			"weigh_bridge_measurement": wbm_name,
			"is_local_procurement": 0,
		}
	)
	if cint(wbm.is_farmer_or_agent) and not (payload.get("agent_name") or "").strip():
		agent_name = (wbm.agent_name or "").strip() or get_rst_agent_name(
			demo_rst_data=wbm.demo_rst_data, rst_no=rst_no
		) or ""
		if agent_name:
			payload["agent_name"] = agent_name
	return payload


def grn_dict_for_local_wbm(wbm_name: str) -> dict | None:
	"""Initial GRN payload for local / farmer–agent WBM (no transit pass)."""
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return None
	if not is_local_procurement_wbm(wbm_name):
		return None

	wbm = frappe.db.get_value(
		"Weigh Bridge Measurement",
		wbm_name,
		[
			"rst_no",
			"agent_name",
			"demo_rst_data",
			"load_weight",
			"gross_weight",
			"tare_weight",
			"net_weight",
			"deduction",
			"gunny_type",
			"gunny_weight",
			"vehicle_no",
			"commodity",
			"date",
			"measurement_date",
			"measurement_time",
			"quality_check",
			"gate_entry",
		],
		as_dict=True,
	)
	if not wbm or not (wbm.rst_no or "").strip():
		return None

	rst = None
	if (wbm.demo_rst_data or "").strip() and frappe.db.exists("RST Details", wbm.demo_rst_data):
		rst = frappe.db.get_value(
			"RST Details",
			wbm.demo_rst_data,
			["party_name", "commodity", "entry_date", "entry_time"],
			as_dict=True,
		)

	return {
		"doctype": "GRN Note",
		"is_local_procurement": 1,
		"is_farmer_or_agent": 1,
		"pass_unique_key": "",
		"rst_no": wbm.rst_no,
		"weigh_bridge_measurement": wbm_name,
		"agent_name": "",
		"receipt_datetime": (
			get_datetime(wbm.date)
			if wbm.date
			else get_datetime(
				f"{(rst.entry_date if rst else None) or wbm.measurement_date or nowdate()} "
				f"{(rst.entry_time if rst else None) or wbm.measurement_time or nowtime()}"
			)
		),
		"ppc_name": ((rst.party_name or "").strip() if rst else ""),
		"paddy_variety": ((rst.commodity if rst else "") or wbm.commodity or "").strip(),
		"gross_vehicle_weight": flt(wbm.load_weight),
		"gross_weight": flt(wbm.gross_weight),
		"tare_weight": flt(wbm.tare_weight),
		"net_weight": flt(wbm.net_weight),
		"deduction": flt(wbm.deduction),
		"gunny_type": wbm.gunny_type or "",
		"gunny_weight": flt(wbm.gunny_weight),
		"vehicle_no": normalize_vehicle_no(wbm.actual_truck_no or wbm.vehicle_no),
		"quality_check": (wbm.quality_check or "").strip(),
		"gate_entry": (wbm.gate_entry or "").strip(),
	}


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
		_TP_SYNC_FIELDS,
		as_dict=True,
	)
	if not tp:
		return {}
	mill_display = (tp.miller or "").strip()
	mill_link = resolve_mill_master_name(key, tp.miller) or ""
	ppc_link = resolve_ppc_master_name(tp.ppc) or ""
	season_link = resolve_season_master_name(tp.season) or ""
	chhatni = (
		get_chhatni_from_season_mapping(season_link, ppc_link, mill_link)
		if mill_link and ppc_link and season_link
		else 0
	)
	tp_datetime = _transit_pass_datetime_from_row(tp)
	return {
		"cmr_season": (tp.season or "").strip(),
		"transit_pass_no": tp.transit_pass_no,
		"transit_pass_date": tp.transit_pass_date,
		"transit_pass_datetime": tp_datetime,
		"tp_quantity": flt(tp.quantity),
		"pacs": (tp.pacs or "").strip(),
		"ppc": (tp.ppc or "").strip(),
		"mill_name": mill_display,
		"chhatni": chhatni,
		"entry_details": _entry_rows_for_pass(key),
	}


def _grn_details_from_rst(
	rst_no: str, pass_unique_key: str | None = None, strict_wbm: bool = True
) -> dict:
	rst_no = (rst_no or "").strip()
	wbm_name = _resolve_wbm_for_rst(rst_no, pass_unique_key)
	if not wbm_name and not (pass_unique_key or "").strip():
		wbm_name = _resolve_wbm_for_rst(rst_no, None)
	if not wbm_name:
		return {"error": _("No Weigh Bridge Measurement found for RST No {0}.").format(rst_no)}

	doc = frappe.new_doc("GRN Note")
	local = is_local_procurement_wbm(wbm_name)
	doc.is_local_procurement = 1 if local else 0
	doc.pass_unique_key = "" if local else (pass_unique_key or "").strip()
	doc.rst_no = rst_no
	doc.weigh_bridge_measurement = wbm_name
	if local:
		doc._sync_local_procurement_flags()
	doc._apply_weigh_bridge(wbm_name, strict=strict_wbm and not local)
	if local:
		doc._sync_local_procurement_from_rst()
	if doc.quality_check:
		doc._apply_quality_check(doc.quality_check)
	if doc.gate_entry:
		doc._apply_gate_entry(doc.gate_entry)

	return {
		"is_local_procurement": doc.is_local_procurement,
		"local_procurement_note": doc.local_procurement_note,
		"weigh_bridge_measurement": wbm_name,
		"gross_vehicle_weight": doc.gross_vehicle_weight,
		"gross_weight": doc.gross_weight,
		"tare_weight": doc.tare_weight,
		"net_weight": doc.net_weight,
		"deduction": doc.deduction,
		"gunny_type": doc.gunny_type,
		"gunny_weight": doc.gunny_weight,
		"gate_entry": doc.gate_entry,
		"vehicle_no": doc.vehicle_no,
		"driver_name": doc.driver_name,
		"arrival_date": doc.arrival_date,
		"arrival_time": doc.arrival_time,
		"gate_exit": doc.gate_exit,
		"gate_exit_date": doc.gate_exit_date,
		"gate_out_time": doc.gate_out_time,
		"quality_check": doc.quality_check,
		"qc_sample_no": doc.qc_sample_no,
		"no_of_bags": doc.no_of_bags,
		"moisture": doc.moisture,
		"dust": doc.dust,
		"unloader_name": doc.unloader_name,
		"unloading_point": doc.unloading_point,
		"ppc_name": doc.ppc_name,
		"is_farmer_or_agent": doc.is_farmer_or_agent,
		"agent_name": doc.agent_name,
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
		"jute_bags": cint(doc.jute_bags),
		"plastic_bags": cint(doc.plastic_bags),
		"total_bags": cint(doc.total_bags),
	}


def _wbm_bag_counts_from_child_table(wbm_name: str) -> tuple[int, int, int]:
	wbm_name = (wbm_name or "").strip()
	if not wbm_name or not frappe.db.exists("Weigh Bridge Measurement", wbm_name):
		return 0, 0, 0

	rows = frappe.get_all(
		"Weigh Bridge Bag Detail",
		filters={
			"parent": wbm_name,
			"parenttype": "Weigh Bridge Measurement",
			"parentfield": "bag_weight_details",
		},
		fields=["jute_bags", "plastic_bags"],
		order_by="idx asc",
	)
	jute = sum(cint(row.jute_bags) for row in rows)
	plastic = sum(cint(row.plastic_bags) for row in rows)
	wbm_total = frappe.db.get_value("Weigh Bridge Measurement", wbm_name, "total_bags")
	total = cint(wbm_total) if wbm_total is not None else jute + plastic
	return jute, plastic, total


@frappe.whitelist()
def get_transit_pass_details(pass_unique_key):
	return _transit_pass_payload(pass_unique_key)


@frappe.whitelist()
def refresh_tp_fulfillment_on_grn(name):
	"""Refresh TP/Chhatni status fields for display (government GRN)."""
	doc = frappe.get_doc("GRN Note", name)
	if cint(doc.is_local_procurement) or not (doc.pass_unique_key or "").strip():
		return {}
	refresh_tp_fulfillment_for_pass(doc.pass_unique_key)
	return frappe.db.get_value(
		"GRN Note",
		name,
		[
			"received_quantity",
			"tp_cumulative_received",
			"tp_chhatni_balance",
			"tp_fulfillment_status",
			"chhatni_fulfillment_status",
			"chhatni_fulfillment_remark",
		],
		as_dict=True,
	)


@frappe.whitelist()
def fetch_chhatni_for_grn(
	pass_unique_key=None, mill_name=None, ppc=None, ppc_name=None, cmr_season=None
):
	mill_link = resolve_mill_master_name(pass_unique_key, mill_name) or ""
	ppc_link = resolve_ppc_master_name(ppc) or resolve_ppc_master_name(ppc_name)
	season_link = resolve_season_master_name(cmr_season)
	if not (mill_link and ppc_link and season_link):
		return 0
	return get_chhatni_from_season_mapping(season_link, ppc_link, mill_link)


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


def _grn_receipt_datetime_display(doc) -> str:
	receipt_dt = combine_datetime(doc, "receipt_datetime", "receipt_date", "receipt_time")
	if not receipt_dt:
		return "—"
	return format_datetime(receipt_dt)


def _grn_transit_pass_datetime_display(doc) -> str:
	tp_dt = combine_datetime(doc, "transit_pass_datetime", "transit_pass_date", None)
	if not tp_dt:
		return "—"
	return format_datetime(tp_dt)


def _format_grn_qty(value) -> str:
	if value is None or (isinstance(value, str) and not str(value).strip()):
		return "—"
	text = f"{flt(value):,.3f}"
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return text


def _reload_grn_for_print(name: str):
	doc = frappe.get_doc("GRN Note", name)
	if cint(doc.is_local_procurement) or not (doc.pass_unique_key or "").strip():
		return doc
	refresh_tp_fulfillment_for_pass((doc.pass_unique_key or "").strip())
	return frappe.get_doc("GRN Note", name)


def _render_grn_note_pass_html(doc, for_pdf: bool = False) -> str:
	receipt_datetime_display = _grn_receipt_datetime_display(doc)
	qr_text = qr_content_grn_note(doc, receipt_datetime_display)
	purchase_heading = (doc.local_procurement_note or "").strip()
	if not purchase_heading:
		purchase_heading = (
			_("Local Paddy Purchase") if cint(doc.is_local_procurement) else _("Government Paddy Purchase")
		)
	tp_qty = flt(doc.tp_quantity)
	tp_cumulative = flt(doc.tp_cumulative_received)
	tp_pass_fulfilled = tp_qty > 0 and tp_cumulative >= tp_qty
	chhatni_display_status = (doc.chhatni_fulfillment_status or "").strip()
	if not chhatni_display_status and tp_pass_fulfilled:
		chhatni_display_status = chhatni_fulfillment_status(
			tp_qty,
			tp_cumulative,
			flt(doc.chhatni),
		)

	return render_template_file(
		("procurement", "doctype", "grn_note", "grn_note_pass.html"),
		{
			"doc": doc,
			"receipt_datetime_display": receipt_datetime_display,
			"transit_pass_datetime_display": _grn_transit_pass_datetime_display(doc),
			"purchase_heading": purchase_heading,
			"qty_received": _format_grn_qty(doc.received_quantity),
			"qty_cumulative": _format_grn_qty(doc.tp_cumulative_received),
			"qty_tp_chhatni_balance": _format_grn_qty(doc.tp_chhatni_balance),
			"qty_tp": _format_grn_qty(doc.tp_quantity),
			"tp_pass_fulfilled": tp_pass_fulfilled,
			"chhatni_display_status": chhatni_display_status,
			"qr_image": qr_image_html(qr_text, size=118),
			"qr_text": qr_text,
			"for_pdf": for_pdf,
		},
	)


def _sync_procurement_rollups_for_pass(pass_unique_key: str) -> None:
	from ivri_od.procurement.procurement_sync import sync_procurement_from_pass

	sync_procurement_from_pass((pass_unique_key or "").strip())


@frappe.whitelist()
def get_grn_note_pass_html(name: str) -> str:
	frappe.get_doc("GRN Note", name).check_permission("print")
	doc = _reload_grn_for_print(name)
	return _render_grn_note_pass_html(doc)


@frappe.whitelist()
def download_grn_note_pass_pdf(name: str):
	frappe.get_doc("GRN Note", name).check_permission("print")
	doc = _reload_grn_for_print(name)
	html = _render_grn_note_pass_html(doc, for_pdf=True)
	label = (doc.grn_no or doc.name or "grn").replace("/", "-")
	send_pdf_download(html, f"{label}-grn.pdf")
