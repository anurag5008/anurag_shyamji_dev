# Copyright (c) 2026, Profezzo and contributors

import frappe
from frappe.utils import cint


def get_weigh_bridge_bags_for_tp(pass_unique_key: str, exclude_wbm: str | None = None) -> int:
	key = (pass_unique_key or "").strip()
	if not key:
		return 0

	total = 0
	for row in frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"pass_unique_key": key},
		fields=["name", "no_of_bags"],
	):
		if exclude_wbm and row.name == exclude_wbm:
			continue
		total += cint(row.no_of_bags)
	return total


def get_quality_check_bags_for_tp(
	pass_unique_key: str, exclude_qc: str | None = None
) -> int:
	key = (pass_unique_key or "").strip()
	if not key:
		return 0

	total = 0
	for row in frappe.get_all(
		"Quality Check",
		filters={"pass_unique_key": key},
		fields=["name", "bag_received", "paddy_return_bags"],
	):
		if exclude_qc and row.name == exclude_qc:
			continue
		total += cint(row.bag_received) + cint(row.paddy_return_bags)

	return total


def get_other_qc_bags_for_tp(pass_unique_key: str, exclude_qc: str | None = None) -> int:
	return get_quality_check_bags_for_tp(pass_unique_key, exclude_qc)


def bag_remaining_for_tp(
	pass_unique_key: str,
	total_bags_in_tp,
	bag_received,
	paddy_return_bags,
	exclude_qc: str | None = None,
) -> int:
	tp_bags = cint(total_bags_in_tp)
	if not pass_unique_key:
		return max(0, tp_bags - cint(bag_received) - cint(paddy_return_bags))

	other_qc = get_other_qc_bags_for_tp(pass_unique_key, exclude_qc)
	accounted = other_qc + cint(bag_received) + cint(paddy_return_bags)
	return max(0, tp_bags - accounted)
