# Copyright (c) 2026, Profezzo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from ivri_od.procurement import vehicle_statement as vs


class VehicleWiseStatement(Document):
	def validate(self):
		self.check_statement_type()
		self.recalculate()

	def check_statement_type(self):
		"""Only the Paddy statement is built; CMR (rice) comes later."""
		if not self.statement_type:
			self.statement_type = "Paddy"
		if self.statement_type == "CMR":
			frappe.throw(_("The CMR (rice) statement is not ready yet. Choose Paddy."))

	def recalculate(self):
		"""One row for each vehicle and PPC. Amount = Qty x Rate (the KM is only noted). Hired vehicles first, then own vehicles; the rows of a vehicle stay together.
		The S.L No and the Voucher No are for the vehicle (on its first row): the vouchers follow the vehicle's total amount. Payment Mode is for hired vehicles only
		(an own vehicle is under an undertaking: no voucher, no payment mode). Then the totals; the same rules the screen shows while typing."""
		own = {vs.normal_vehicle(v) for v in vs.own_vehicle_numbers()}
		rows = list(self.get("items") or [])
		for row in rows:
			row.vehicle_type = vs.OWN if vs.normal_vehicle(row.vehicle_no) in own else vs.HIRED
			row.amount = vs.amount_of(row.qty, row.rate)
		rows.sort(key=lambda row: (row.vehicle_type == vs.OWN, vs.normal_vehicle(row.vehicle_no)))  # stable: the PPC order of a vehicle is kept
		self.items = rows
		for index, row in enumerate(rows, 1):
			row.idx = index
		groups = []  # the rows of each vehicle
		for row in rows:
			if groups and vs.normal_vehicle(groups[-1][0].vehicle_no) == vs.normal_vehicle(row.vehicle_no):
				groups[-1].append(row)
			else:
				groups.append([row])
		hired = [g for g in groups if g[0].vehicle_type != vs.OWN]
		own_groups = [g for g in groups if g[0].vehicle_type == vs.OWN]
		vouchers = vs.assign_vouchers([sum(flt(row.amount) for row in g) for g in hired])
		for serial, (group, voucher_no) in enumerate(zip(hired, vouchers), 1):
			for position, row in enumerate(group):
				row.payment_mode = vs.PAYMENT_MODE
				row.sl_no = str(serial) if position == 0 else ""
				row.voucher_no = voucher_no if position == 0 else ""
		for group in own_groups:
			for row in group:
				row.sl_no = ""
				row.payment_mode = ""
				row.voucher_no = ""
		hired_rows = [row for g in hired for row in g]
		own_rows = [row for g in own_groups for row in g]
		self.total_vehicles = len(groups)
		self.hired_qty = flt(sum(flt(row.qty) for row in hired_rows), 2)
		self.hired_amount = flt(sum(flt(row.amount) for row in hired_rows), 2)
		self.own_qty = flt(sum(flt(row.qty) for row in own_rows), 2)
		self.own_amount = flt(sum(flt(row.amount) for row in own_rows), 2)
		self.total_qty = flt(self.hired_qty + self.own_qty, 2)  # G. Total
		self.total_amount = flt(self.hired_amount + self.own_amount, 2)  # G. Total
		self.total_vouchers = sum(vs.vouchers_needed(sum(flt(row.amount) for row in g)) for g in hired)
		self.kms_title = vs.kms_title(self.season)

	@frappe.whitelist()
	def fetch_details(self):
		"""Fill the table from the PPAS Transit Passes. The KM and Rate already typed for a vehicle and PPC are kept when it is fetched again."""
		self.check_statement_type()
		if not self.miller or not self.season:
			frappe.throw(_("Choose the Miller and the Season first."))
		passes = vs.get_passes(self.miller, self.season, self.district)
		if not passes:
			frappe.throw(_("No PPAS Transit Pass found for these filters."))
		typed = {(vs.normal_vehicle(row.vehicle_no), (row.ppc or "").strip()): (row.km, row.rate) for row in self.get("items") or []}
		self.set("items", [])
		entries = vs.vehicle_rows(passes, vs.own_vehicle_numbers())
		distances = vs.ppc_distances(vs.code_of(entry["ppc"]) for entry in entries)  # the KM comes from the Distance of the PPC in the PPC Master
		for entry in entries:
			km, rate = typed.get((entry["vehicle_no"], entry["ppc"]), (0, 0))
			km = distances.get(vs.code_of(entry["ppc"])) or km  # a PPC without a Distance there keeps the KM typed before
			self.append("items", {"vehicle_no": entry["vehicle_no"], "ppc": entry["ppc"], "bags": entry["bags"], "trips": entry["trips"], "qty": entry["qty"], "km": km, "rate": rate})
		self.recalculate()
		return len(self.items)


@frappe.whitelist()
def get_filter_options():
	"""The millers and seasons found in the PPAS Transit Passes, to choose from."""
	return {
		"millers": frappe.get_all("PPAS Transit Pass", filters={"miller": ["is", "set"]}, pluck="miller", distinct=True, order_by="miller asc"),
		"seasons": frappe.get_all("PPAS Transit Pass", filters={"season": ["is", "set"]}, pluck="season", distinct=True, order_by="season asc"),
	}
