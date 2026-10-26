# Copyright (c) 2026, Profezzo and contributors
"""Masked demo data to test Stock Account for Paddy on a test site (never on a live site).

Creates a demo mill, district, PPCs and transit passes, then runs every truck through the normal
weighment flow (Gate Entry -> Quality Check -> RST Details -> Weigh Bridge -> Gate Exit -> GRN Note).
No DCRO rows are made: Issue for Milling comes only from paddy release rows read from the portal.

	bench --site <site> execute ivri_od.procurement.report.stock_account_for_paddy.demo_data.create_demo_data
	bench --site <site> execute ivri_od.procurement.report.stock_account_for_paddy.demo_data.delete_demo_data

Report filters: Mill Name M999901, KMS Year 25-26, District DEMO DISTRICT, Nov-25 to Jan-26.
Expected: PACs 220 / 200 / 240 (Kharif and Rabi), Issue for Milling 0 / 0 / 0, CB 220 / 420 / 660.

create_tp_demo_data weighs trucks against transit passes already on the site (read from PPAS)
of one PPC or one mill (count 0 = every free pass), in a mix of cases, and prints the PACs each
month should show:

	bench --site <site> execute <this module>.create_tp_demo_data --kwargs "{'ppc': 'PATUAPALI', 'count': 8}"
	bench --site <site> execute <this module>.create_tp_demo_data --kwargs "{'mill': 'M051007', 'count': 0}"
	bench --site <site> execute <this module>.delete_tp_demo_data
"""

import frappe
from collections import defaultdict

from frappe.utils import add_days, flt, getdate

from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass

MILL = "M999901"
MILL_NAME = "DEMO RICE MILL"
MILL_TEXT = f"{MILL_NAME}({MILL})"
DISTRICT = "DEMO DISTRICT"
OTHER_DISTRICT = "DEMO DISTRICT TWO"
KMS_YEAR = "2025"
RST_PREFIX = "DEMO-RST-"
# Weighments made against transit passes already on the site.
TP_RST_PREFIX = "DEMO-TPRST-"

PPCS = [
	# (code, name, district)
	("SDEMO01", "DEMO PPC ONE", DISTRICT),
	("SDEMO02", "DEMO PPC TWO", DISTRICT),
	("SDEMO03", "DEMO PPC THREE", OTHER_DISTRICT),
]

# (TP no, PPC code, TP quantity, [(RST date, net weight), ...], crop) - one truck per weighment.
TRANSIT_PASSES = [
	# Fulfilled over two months: Nov 120 + Dec 90 = 210 -> counts 200 (120 in Nov, 80 in Dec).
	("9001", "SDEMO01", 200, [("2025-11-10", 120), ("2025-12-05", 90)], "Kharif"),
	# Short: 100 of 150 received -> counts 100 in Nov.
	("9002", "SDEMO01", 150, [("2025-11-18", 100)], "Kharif"),
	# Three trucks: Dec 60 + Dec 60 + Jan 70 = 190 -> counts 180 (60, 60 in Dec, 60 in Jan).
	("9003", "SDEMO02", 180, [("2025-12-12", 60), ("2025-12-20", 60), ("2026-01-08", 70)], "Kharif"),
	# Over TP in one truck: 105 of 100 -> counts 100 in Jan.
	("9004", "SDEMO02", 100, [("2026-01-15", 105)], "Kharif"),
	# PPC in another district: not in the DEMO DISTRICT statement.
	("9005", "SDEMO03", 50, [("2026-01-20", 50)], "Kharif"),
	# Rabi pass of the same KMS Year: counts 80 in Jan, with the Kharif passes.
	("9006", "SDEMO01", 80, [("2026-01-25", 80)], "Rabi"),
]

# Trucks per transit pass for create_tp_demo_data, used in turn:
# [(days after the TP was accepted, share of the TP quantity), ...]
TP_CASES = [
	("fulfilled, one truck", [(0, 1.0)]),
	("fulfilled, two trucks in two months", [(0, 0.5), (30, 0.52)]),
	("short", [(0, 0.9)]),
	("over TP, one truck", [(0, 1.03)]),
	("fulfilled, three trucks", [(0, 0.35), (12, 0.35), (32, 0.32)]),
	("fulfilled, next month", [(25, 1.0)]),
	("short, two trucks in two months", [(0, 0.5), (30, 0.3)]),
]

TARE_QT = 100.0


def create_demo_data():
	"""Create the demo masters, transit passes, and weighments (with GRN Notes)."""
	if frappe.db.exists("Mill Master", MILL):
		frappe.throw("Demo data exists already. Run delete_demo_data first.")

	_create_masters()
	for tp_no, ppc_code, tp_qty, trucks, crop in TRANSIT_PASSES:
		ppc_text = _ppc_text(ppc_code)
		_create_transit_pass(tp_no, ppc_text, tp_qty, crop)
		for truck_no, (rst_date, net_qt) in enumerate(trucks, 1):
			_weigh_truck(tp_no, truck_no, ppc_text, rst_date, net_qt)

	frappe.db.commit()
	grns = frappe.get_all("GRN Note", filters={"pass_unique_key": ["like", f"{MILL}-%"]}, pluck="name")
	print(f"Demo data created: {len(grns)} GRN Notes for mill {MILL}.")


def delete_demo_data():
	"""Delete everything create_demo_data made: found from the demo RST numbers and the demo miller
	text, so a run that stopped half way is cleaned up too."""
	_delete_weighments(RST_PREFIX)
	_delete("PPAS Transit Pass", _names("PPAS Transit Pass", {"miller": ["like", f"{MILL_NAME}(%"]}))
	_delete("PPC Master", [code for code, _name, _district in PPCS])
	_delete("Mill Master", [MILL])
	_delete("District Master", [DISTRICT, OTHER_DISTRICT])

	frappe.db.commit()
	print("Demo data deleted.")


def create_tp_demo_data(ppc=None, mill=None, count=8):
	"""Weigh trucks against the first ``count`` transit passes (all when count is 0) of a PPC or a
	mill that have no GRN Note yet. Each pass is saved on its own: a pass that fails is listed and skipped."""
	if not (ppc or mill):
		frappe.throw("Give a ppc or a mill.")
	filters = {}
	if ppc:
		ppc_code = frappe.db.get_value("PPC Master", {"ppc_name": ppc}, "name") or ppc
		filters["ppc"] = ["like", f"%({ppc_code})"]
	if mill:
		filters["pass_unique_key"] = ["like", f"{mill}-%"]
	passes = frappe.get_all(
		"PPAS Transit Pass",
		filters=filters,
		fields=[
			"transit_pass_no",
			"ppc",
			"quantity",
			"pass_unique_key",
			"vehicle_no",
			"transit_pass_date",
			"accepted_date",
		],
		order_by="transit_pass_date asc, transit_pass_no asc",
		limit_page_length=0,
	)
	used = set(frappe.get_all("GRN Note", filters={"pass_unique_key": ["is", "set"]}, pluck="pass_unique_key"))
	passes = [tp for tp in passes if tp.pass_unique_key not in used and flt(tp.quantity) > 0]
	if int(count or 0):
		passes = passes[: int(count)]
	if not passes:
		frappe.throw("No transit pass is free to weigh.")

	expected = defaultdict(float)
	failed = []
	for index, tp in enumerate(passes):
		case, trucks = TP_CASES[index % len(TP_CASES)]
		base = getdate(tp.accepted_date or tp.transit_pass_date)
		# PPC code and season code of the pass keep RST numbers unique: "...-PATUAPALI(S1050105)-K25-TP34".
		_mill, ppc_part, season_code, _tp = (tp.pass_unique_key.split("-") + ["", "", "", ""])[:4]
		ppc_code = ppc_part.rpartition("(")[2].rstrip(")") or ppc_part
		month_counted = defaultdict(float)
		received = 0.0
		try:
			for truck_no, (days, share) in enumerate(trucks, 1):
				truck_date = add_days(base, days)
				net_qt = flt(tp.quantity * share, 2)
				_weigh_truck(
					tp.transit_pass_no,
					truck_no,
					tp.ppc,
					str(truck_date),
					net_qt,
					rst_prefix=f"{TP_RST_PREFIX}{ppc_code}-{season_code}-",
					vehicle=tp.vehicle_no,
				)
				# PACs rule: a pass counts at most its TP quantity.
				counted = min(received + net_qt, tp.quantity) - min(received, tp.quantity)
				received += net_qt
				month_counted[getdate(truck_date).strftime("%b-%y")] += counted
			frappe.db.commit()
		except Exception as e:
			frappe.db.rollback()
			failed.append(f"TP {tp.transit_pass_no} {tp.ppc}: {e}")
			continue
		for month, qty in month_counted.items():
			expected[month] += qty

	print(f"Weighed {len(passes) - len(failed)} of {len(passes)} transit passes.")
	for line in failed:
		print("  failed:", line)
	print("Expected PACs:", {month: flt(qty, 2) for month, qty in expected.items()})


def delete_tp_demo_data():
	"""Delete the weighments (and their GRN Notes) made by create_tp_demo_data; transit passes stay."""
	_delete_weighments(TP_RST_PREFIX)
	frappe.db.commit()
	print("Transit pass demo weighments deleted.")


def _delete_weighments(rst_prefix):
	"""Gate Entry, Quality Check, RST, Weigh Bridge, Gate Exit and GRN Note of the demo RST numbers."""
	rsts = frappe.get_all(
		"RST Details",
		filters={"rst_no": ["like", f"{rst_prefix}%"]},
		fields=["name", "weigh_bridge_measurement"],
	)
	wbms = [rst.weigh_bridge_measurement for rst in rsts if rst.weigh_bridge_measurement]
	grns = frappe.get_all(
		"GRN Note", filters={"weigh_bridge_measurement": ["in", wbms or [""]]}, fields=["name", "gate_entry"]
	)
	gate_entries = {grn.gate_entry for grn in grns}
	gate_entries |= set(
		frappe.get_all("Weigh Bridge Measurement", filters={"name": ["in", wbms or [""]]}, pluck="gate_entry")
	)
	gate_entries = list(gate_entries - {None, ""}) or [""]

	_delete("GRN Note", [grn.name for grn in grns])
	_delete("Gate Exit", _names("Gate Exit", {"gate_entry_in": ["in", gate_entries]}))
	_delete("Weigh Bridge Measurement", wbms)
	_delete("RST Details", [rst.name for rst in rsts])
	_delete("Quality Check", _names("Quality Check", {"gate_entry": ["in", gate_entries]}))
	_delete("Gate Entry", gate_entries)


def _create_masters():
	company = frappe.db.get_value("Company", {}, "name")
	for district in (DISTRICT, OTHER_DISTRICT):
		if not frappe.db.exists("District Master", district):
			frappe.get_doc({"doctype": "District Master", "district_name": district, "is_active": 1}).insert()
	frappe.get_doc(
		{"doctype": "Mill Master", "miller_code": MILL, "company": company, "type": "RAW", "is_active": 1}
	).insert()
	for code, name, district in PPCS:
		frappe.get_doc(
			{"doctype": "PPC Master", "code": code, "ppc_name": name, "district": district, "is_active": 1}
		).insert()
	for crop in {crop for *_tp, crop in TRANSIT_PASSES}:
		if not frappe.db.exists("Season Master", f"{crop} {KMS_YEAR}"):
			frappe.throw(f"Season Master {crop} {KMS_YEAR} is missing.")


def _ppc_text(code):
	name = next(ppc_name for ppc_code, ppc_name, _district in PPCS if ppc_code == code)
	return f"{name}({code})"


def _create_transit_pass(tp_no, ppc_text, tp_qty, crop):
	key = f"{MILL}-{ppc_text}-{crop[0]}{KMS_YEAR[-2:]}-TP{tp_no}"
	frappe.get_doc(
		{
			"doctype": "PPAS Transit Pass",
			"season": f"{crop}({KMS_YEAR})",
			"pacs": ppc_text,
			"ppc": ppc_text,
			"miller": MILL_TEXT,
			"transit_pass_no": tp_no,
			"pass_unique_key": key,
			"transit_pass_date": "2025-11-01",
			"vehicle_no": f"OD00DM{tp_no}",
			"bags": int(tp_qty * 2),
			"quantity": tp_qty,
			"action": "Accepted",
		}
	).insert()


def _weigh_truck(tp_no, truck_no, ppc_text, rst_date, net_qt, rst_prefix=RST_PREFIX, vehicle=None):
	"""One truck through gate, QC, weighbridge and gate exit; the Gate Exit makes the GRN Note."""
	vehicle = vehicle or f"OD00DM{tp_no}{truck_no}"
	at = f"{rst_date} 10:30:00"
	bags = int(net_qt * 2)

	gate_entry = frappe.get_doc(
		{
			"doctype": "Gate Entry",
			"in_out": "In",
			"in_purpose": "Paddy",
			"vehicle_no": vehicle,
			"party_name": ppc_text,
			"driver_name": "Demo Driver",
			"entry_datetime": at,
		}
	).insert()
	quality_check = frappe.get_doc(
		{
			"doctype": "Quality Check",
			"vehicle_no": vehicle,
			"gate_entry": gate_entry.name,
			"qc_datetime": at,
			"paddy_quality": "Mota",
			"qc_decision": "Accepted",
			"driver_name": "Demo Driver",
			"staff_name": "Demo Staff",
			"unloading_point": "Demo Point",
			"old_new_bags": [{"old_bags": bags, "new_bags": 0}],
			"type_of_pkt": [{"jute_pkt_no": bags, "no_of_plastic_bag": 0}],
		}
	).insert()
	rst = frappe.get_doc(
		{
			"doctype": "RST Details",
			"rst_no": f"{rst_prefix}{tp_no}-{truck_no}",
			"tp_no": tp_no,
			"party_name": ppc_text,
			"vehicle_no": vehicle,
			"entry_datetime": at,
			"entry_date": rst_date,
			"entry_time": "10:30:00",
			"commodity": "Paddy",
			"gross_vehicle_weight_qt": flt(net_qt + TARE_QT, 3),
			"tare_vehicle_weight_qt": TARE_QT,
			"deduction_qt": 0,
			"gunny_weight_qt": 0,
		}
	).insert()
	rst.reload()
	if not rst.weigh_bridge_measurement:
		frappe.throw(f"No Weigh Bridge Measurement was made for {rst.name} (TP status: {rst.tp_status}).")

	wbm = frappe.get_doc("Weigh Bridge Measurement", rst.weigh_bridge_measurement)
	wbm.gate_entry = gate_entry.name
	wbm.quality_check = quality_check.name
	wbm.quality_test = "Accepted"
	wbm.save()

	frappe.get_doc(
		{
			"doctype": "Gate Exit",
			"vehicle_no": vehicle,
			"gate_entry_in": gate_entry.name,
			"out_purpose": "Others",
			"exit_datetime": at,
		}
	).insert()
	grn = frappe.db.get_value(
		"GRN Note", {"weigh_bridge_measurement": wbm.name}, ["name", "pass_unique_key"], as_dict=True
	)
	if not grn:
		frappe.throw(f"No GRN Note was made on Gate Exit for {wbm.name}.")

	# A GRN Note is dated when it is made (Gate Exit). Demo trucks are back-dated to their month,
	# then the pass's TP fulfillment is worked out again in receipt order.
	frappe.db.set_value(
		"GRN Note",
		grn.name,
		{"receipt_datetime": at, "receipt_date": rst_date, "receipt_time": "10:30:00"},
		update_modified=False,
	)
	refresh_tp_fulfillment_for_pass(grn.pass_unique_key)


def _names(doctype, filters):
	return frappe.get_all(doctype, filters=filters, pluck="name")


def _delete(doctype, names):
	for name in names:
		if name and frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
