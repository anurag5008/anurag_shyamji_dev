"""Integration test: GRN chhatni locked after first save; TA updates Season Mapping only."""

from __future__ import annotations

import frappe
from frappe.utils import nowdate, nowtime

PASS_KEY = "M051007-AGALPUR(S1050118)-K25-TP28"
TP_NO = "28"
PPC_PARTY = "AGALPUR(S1050118)"
SEASON = "Kharif 2025"
PPC_LINK = "S1050118"
MILL = "M051007"
INITIAL_CHHATNI = 5.5
UPDATED_CHHATNI = 8.8


def debug_resolve():
	from ivri_od.procurement.doctype.season_master.season_master import resolve_season_master_name
	from ivri_od.procurement.transit_pass_resolve import resolve_mill_master_name, resolve_ppc_master_name
	from ivri_od.procurement.doctype.season_mapping.season_mapping import get_chhatni_from_season_mapping

	print("season", resolve_season_master_name("Kharif(2025)"))
	print("ppc", resolve_ppc_master_name("AGALPUR(S1050118)"))
	print("mill", resolve_mill_master_name(PASS_KEY, "SHREE SHYAMJI PADDY PROCESSING PVT LTD(M051007)"))
	print(
		"chhatni",
		get_chhatni_from_season_mapping(
			resolve_season_master_name("Kharif(2025)"),
			resolve_ppc_master_name("AGALPUR(S1050118)"),
			resolve_mill_master_name(PASS_KEY, ""),
		),
	)


def run():
	frappe.set_user("Administrator")
	rst_no = _unique_rst_no()
	ta_name = frappe.db.get_value(
		"Target Allocation",
		{"season": SEASON, "ppc_name": PPC_LINK, "mill_name": MILL},
		"name",
	)
	original_chhatni = flt(
		frappe.db.get_value("Target Allocation", ta_name, "chhatni") if ta_name else 0
	)
	ta_name = _ensure_target_allocation(INITIAL_CHHATNI)
	_assert_season_mapping_chhatni(INITIAL_CHHATNI)

	rst = _create_rst(rst_no)
	wbm = (rst.weigh_bridge_measurement or "").strip()
	if not wbm:
		frappe.throw(f"RST {rst_no}: weigh bridge was not created")
	_prepare_wbm_for_grn(wbm)

	grn = _create_grn(rst_no, PASS_KEY)
	chhatni_after_create = frappe.db.get_value("GRN Note", grn.name, "chhatni")
	row = frappe.db.get_value(
		"GRN Note",
		grn.name,
		["mill_name", "ppc", "cmr_season", "chhatni"],
		as_dict=True,
	)
	print(f"GRN {grn.name} after create: {row}")
	if flt(chhatni_after_create) != INITIAL_CHHATNI:
		_cleanup(rst_no, grn.name, ta_name)
		frappe.throw(
			f"Expected GRN chhatni {INITIAL_CHHATNI}, got {chhatni_after_create}"
		)

	_update_target_allocation_chhatni(ta_name, UPDATED_CHHATNI)
	_assert_season_mapping_chhatni(UPDATED_CHHATNI)

	grn_doc = frappe.get_doc("GRN Note", grn.name)
	grn_doc.receipt_date = grn_doc.receipt_date or nowdate()
	grn_doc.save(ignore_permissions=True)
	chhatni_after_resave = frappe.db.get_value("GRN Note", grn.name, "chhatni")
	print(f"GRN {grn.name} chhatni after TA change + GRN resave: {chhatni_after_resave}")

	if flt(chhatni_after_resave) != INITIAL_CHHATNI:
		_cleanup(rst_no, grn.name, ta_name, reset_chhatni=original_chhatni or INITIAL_CHHATNI)
		frappe.throw(
			f"GRN chhatni changed after Target Allocation update: "
			f"expected {INITIAL_CHHATNI}, got {chhatni_after_resave}"
		)

	print("PASS: GRN chhatni stayed fixed; Season Mapping followed Target Allocation.")
	frappe.db.commit()
	result = {
		"grn": grn.name,
		"chhatni_locked": chhatni_after_resave,
		"season_mapping_chhatni": UPDATED_CHHATNI,
	}
	try:
		_cleanup(rst_no, grn.name, ta_name, reset_chhatni=original_chhatni or INITIAL_CHHATNI)
	except Exception as exc:
		print(f"Cleanup warning (test passed): {exc}")
	return result


def _unique_rst_no() -> str:
	import random

	return f"TST-CHH-{random.randint(100000, 999999)}"


def _ensure_target_allocation(chhatni: float) -> str:
	name = frappe.db.get_value(
		"Target Allocation",
		{"season": SEASON, "ppc_name": PPC_LINK, "mill_name": MILL},
		"name",
	)
	if not name:
		frappe.throw("Missing Target Allocation for test PPC/Mill/Season")
	frappe.db.set_value("Target Allocation", name, "chhatni", chhatni, update_modified=True)
	doc = frappe.get_doc("Target Allocation", name)
	doc.save(ignore_permissions=True)
	return name


def _update_target_allocation_chhatni(name: str, chhatni: float):
	frappe.db.set_value("Target Allocation", name, "chhatni", chhatni, update_modified=True)
	doc = frappe.get_doc("Target Allocation", name)
	doc.save(ignore_permissions=True)


def _assert_season_mapping_chhatni(expected: float):
	value = frappe.db.get_value(
		"Season Mapping",
		{"season": SEASON, "ppc_name": PPC_LINK, "mill_name": MILL},
		"chhatni",
	)
	print(f"Season Mapping chhatni: {value} (expected {expected})")
	if flt(value) != expected:
		frappe.throw(f"Season Mapping chhatni expected {expected}, got {value}")


def _prepare_wbm_for_grn(wbm_name: str):
	wbm = frappe.get_doc("Weigh Bridge Measurement", wbm_name)
	if not flt(wbm.tare_weight):
		wbm.tare_weight = 2
	wbm.quality_test = "Accepted"
	wbm.flags.ignore_validate = True
	wbm.save(ignore_permissions=True)


def _create_rst(rst_no: str):
	doc = frappe.get_doc(
		{
			"doctype": "RST Details",
			"rst_no": rst_no,
			"party_name": PPC_PARTY,
			"tp_no": TP_NO,
			"vehicle_no": "OD99T9999",
			"gross_vehicle_weight_qt": 10,
			"tare_vehicle_weight_qt": 2,
			"gross_paddy_weight_qt": 8,
			"net_paddy_weight_qt": 7.5,
			"commodity": "Test Paddy",
			"entry_date": nowdate(),
			"entry_time": nowtime(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _create_grn(rst_no: str, pass_key: str):
	doc = frappe.get_doc(
		{
			"doctype": "GRN Note",
			"receipt_date": nowdate(),
			"receipt_time": nowtime(),
			"pass_unique_key": pass_key,
			"rst_no": rst_no,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _cleanup(rst_no: str, grn_name: str, ta_name: str, reset_chhatni: float | None = None):
	for name in (grn_name,):
		if name and frappe.db.exists("GRN Note", name):
			frappe.delete_doc("GRN Note", name, force=True, ignore_permissions=True)
	frappe.db.commit()
	if rst_no and frappe.db.exists("RST Details", rst_no):
		frappe.delete_doc("RST Details", rst_no, force=True, ignore_permissions=True)
	if reset_chhatni is not None and ta_name:
		frappe.db.set_value("Target Allocation", ta_name, "chhatni", reset_chhatni, update_modified=True)
		frappe.get_doc("Target Allocation", ta_name).save(ignore_permissions=True)
	frappe.db.commit()


def flt(value):
	from frappe.utils import flt as _flt

	return _flt(value)
