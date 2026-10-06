# Copyright (c) 2026, Profezzo and contributors

import frappe


def execute():
	_backfill_quality_check()
	_backfill_grn_note()
	_backfill_wbm_date_from_legacy()


def _backfill_quality_check():
	if not frappe.db.has_column("Quality Check", "qc_datetime"):
		return
	frappe.db.sql(
		"""
		update `tabQuality Check`
		set qc_datetime = timestamp(qc_date, coalesce(qc_time, '00:00:00'))
		where qc_datetime is null and qc_date is not null
		"""
	)


def _backfill_grn_note():
	if not frappe.db.has_column("GRN Note", "receipt_datetime"):
		return
	frappe.db.sql(
		"""
		update `tabGRN Note`
		set receipt_datetime = timestamp(receipt_date, coalesce(receipt_time, '00:00:00'))
		where receipt_datetime is null and receipt_date is not null
		"""
	)
	frappe.db.sql(
		"""
		update `tabGRN Note`
		set arrival_datetime = timestamp(arrival_date, coalesce(arrival_time, '00:00:00'))
		where arrival_datetime is null and arrival_date is not null
		"""
	)
	frappe.db.sql(
		"""
		update `tabGRN Note`
		set gate_exit_datetime = timestamp(gate_exit_date, coalesce(gate_out_time, '00:00:00'))
		where gate_exit_datetime is null and gate_exit_date is not null
		"""
	)


def _backfill_wbm_date_from_legacy():
	if not frappe.db.has_column("Weigh Bridge Measurement", "date"):
		return
	frappe.db.sql(
		"""
		update `tabWeigh Bridge Measurement`
		set date = timestamp(measurement_date, coalesce(measurement_time, '00:00:00'))
		where (date is null) and measurement_date is not null
		"""
	)
