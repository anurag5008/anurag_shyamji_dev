# Copyright (c) 2026, Profezzo and contributors
"""Masked demo data to test Stock Account for Paddy on a test site (never on a live site).

Creates a demo mill, district, PPCs and transit passes, then runs every truck through the normal
weighment flow (Gate Entry -> Quality Check -> RST Details -> Weigh Bridge -> Gate Exit -> GRN Note),
and adds DCRO paddy release rows for the mill.

	bench --site <site> execute ivri_od.procurement.report.stock_account_for_paddy.demo_data.create_demo_data
	bench --site <site> execute ivri_od.procurement.report.stock_account_for_paddy.demo_data.delete_demo_data

Report filters: Mill Name M999901, KMS Year Kharif 2025, District DEMO DISTRICT, Nov-25 to Jan-26.
Expected: PACs 220 / 200 / 160, Issue for Milling 0 / 150 / 200, CB 220 / 270 / 230.
"""

import json

import frappe
from frappe.utils import flt, now_datetime

from ivri_od.procurement.grn_tp_fulfillment import refresh_tp_fulfillment_for_pass
from ivri_od.procurement.portal_sync import build_record_key, build_row_hash, parse_key_columns

MILL = "M999901"
MILL_NAME = "DEMO RICE MILL"
MILL_TEXT = f"{MILL_NAME}({MILL})"
DISTRICT = "DEMO DISTRICT"
OTHER_DISTRICT = "DEMO DISTRICT TWO"
SEASON = "Kharif 2025"
SEASON_TEXT = "Kharif(2025)"
SEASON_CODE = "K25"
RST_PREFIX = "DEMO-RST-"
DEMO_TAG = "(demo)"

PPCS = [
	# (code, name, district)
	("SDEMO01", "DEMO PPC ONE", DISTRICT),
	("SDEMO02", "DEMO PPC TWO", DISTRICT),
	("SDEMO03", "DEMO PPC THREE", OTHER_DISTRICT),
]

# (TP no, PPC code, TP quantity, [(RST date, net weight), ...]) - one truck per weighment.
TRANSIT_PASSES = [
	# Fulfilled over two months: Nov 120 + Dec 90 = 210 -> counts 200 (120 in Nov, 80 in Dec).
	("9001", "SDEMO01", 200, [("2025-11-10", 120), ("2025-12-05", 90)]),
	# Short: 100 of 150 received -> counts 100 in Nov.
	("9002", "SDEMO01", 150, [("2025-11-18", 100)]),
	# Three trucks: Dec 60 + Dec 60 + Jan 70 = 190 -> counts 180 (60, 60 in Dec, 60 in Jan).
	("9003", "SDEMO02", 180, [("2025-12-12", 60), ("2025-12-20", 60), ("2026-01-08", 70)]),
	# Over TP in one truck: 105 of 100 -> counts 100 in Jan.
	("9004", "SDEMO02", 100, [("2026-01-15", 105)]),
	# PPC in another district: not in the DEMO DISTRICT statement.
	("9005", "SDEMO03", 50, [("2026-01-20", 50)]),
]

# DCRO Paddy Release rows: (RO no, date of requisition, own district, other district, status)
DCRO_RELEASES = [
	("DEMO-RO-1", "15-12-2025", 120, 30, "Approved"),
	("DEMO-RO-2", "20-01-2026", 200, 0, "Approved"),
	("DEMO-RO-3", "10-01-2026", 999, 0, "Rejected"),
]

TARE_QT = 100.0


def create_demo_data():
	"""Create the demo masters, transit passes, weighments (with GRN Notes) and DCRO rows."""
	if frappe.db.exists("Mill Master", MILL):
		frappe.throw("Demo data exists already. Run delete_demo_data first.")

	_create_masters()
	for tp_no, ppc_code, tp_qty, trucks in TRANSIT_PASSES:
		ppc_text = _ppc_text(ppc_code)
		_create_transit_pass(tp_no, ppc_text, tp_qty, len(trucks))
		for truck_no, (rst_date, net_qt) in enumerate(trucks, 1):
			_weigh_truck(tp_no, truck_no, ppc_text, rst_date, net_qt)
	_create_dcro_releases()

	frappe.db.commit()
	grns = frappe.get_all("GRN Note", filters={"pass_unique_key": ["like", f"{MILL}-%"]}, pluck="name")
	print(f"Demo data created: {len(grns)} GRN Notes for mill {MILL}.")


def delete_demo_data():
	"""Delete everything create_demo_data made: found from the demo RST numbers, the demo miller
	text and the demo DCRO rows, so a run that stopped half way is cleaned up too."""
	rsts = frappe.get_all(
		"RST Details",
		filters={"rst_no": ["like", f"{RST_PREFIX}%"]},
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
	_delete("PPAS Transit Pass", _names("PPAS Transit Pass", {"miller": ["like", f"{MILL_NAME}(%"]}))
	_delete("Portal Record", _names("Portal Record", {"site": "DCRO", "summary": ["like", f"%{DEMO_TAG}"]}))
	_delete("PPC Master", [code for code, _name, _district in PPCS])
	_delete("Mill Master", [MILL])
	_delete("District Master", [DISTRICT, OTHER_DISTRICT])

	frappe.db.commit()
	print("Demo data deleted.")


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
	if not frappe.db.exists("Season Master", SEASON):
		frappe.throw(f"Season Master {SEASON} is missing.")


def _ppc_text(code):
	name = next(ppc_name for ppc_code, ppc_name, _district in PPCS if ppc_code == code)
	return f"{name}({code})"


def _create_transit_pass(tp_no, ppc_text, tp_qty, trucks):
	key = f"{MILL}-{ppc_text}-{SEASON_CODE}-TP{tp_no}"
	frappe.get_doc(
		{
			"doctype": "PPAS Transit Pass",
			"season": SEASON_TEXT,
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


def _weigh_truck(tp_no, truck_no, ppc_text, rst_date, net_qt):
	"""One truck through gate, QC, weighbridge and gate exit; the Gate Exit makes the GRN Note."""
	vehicle = f"OD00DM{tp_no}{truck_no}"
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
			"rst_no": f"{RST_PREFIX}{tp_no}-{truck_no}",
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


def _create_dcro_releases():
	"""Saved like rows entered by hand (portal_manual.py): key from the section's key columns."""
	section = frappe.get_cached_doc("Portal Site", "DCRO").get_section("Paddy Release")
	key_columns = parse_key_columns(section.key_columns if section else "") or ["RO No."]
	for row_no, (ro_no, requisition_date, own, other, status) in enumerate(DCRO_RELEASES, 1):
		row = {
			"Sl#": str(row_no),
			"RO No.": ro_no,
			"Date of Requistion": requisition_date,
			"Paddy Lifted (Own District) (in Qtl)": "5000.00",
			"Quantity of Paddy Released for Milling (Own District) (in Qtl)": f"{own:.2f}",
			"Paddy Lifted (Other District) (in Qtl)": "0.00",
			"Quantity of Paddy Released for Milling (Other District) (in Qtl)": f"{other:.2f}",
			"Status of Released Order": status,
		}
		frappe.get_doc(
			{
				"doctype": "Portal Record",
				"site": "DCRO",
				"section": "Paddy Release",
				"mill_id": MILL,
				"record_key": build_record_key(row, key_columns),
				"entry_source": "Manual",
				"row_no": row_no,
				"summary": f"{ro_no} {DEMO_TAG}",
				"row_data": json.dumps(row),
				"row_hash": build_row_hash(row),
				"first_seen_on": now_datetime(),
				"last_seen_on": now_datetime(),
			}
		).insert()


def _names(doctype, filters):
	return frappe.get_all(doctype, filters=filters, pluck="name")


def _delete(doctype, names):
	for name in names:
		if name and frappe.db.exists(doctype, name):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
