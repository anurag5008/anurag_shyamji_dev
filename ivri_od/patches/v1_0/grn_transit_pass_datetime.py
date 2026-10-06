# Copyright (c) 2026, Profezzo and contributors

import frappe


def execute():
	frappe.reload_doc("procurement", "doctype", "grn_note")
	if not frappe.db.has_column("GRN Note", "transit_pass_datetime"):
		return
	frappe.db.sql(
		"""
		update `tabGRN Note` g
		inner join `tabPPAS Transit Pass` tp on tp.pass_unique_key = g.pass_unique_key
		set g.transit_pass_datetime = timestamp(
			tp.transit_pass_date,
			coalesce(tp.transit_pass_time, '00:00:00')
		)
		where coalesce(g.pass_unique_key, '') != ''
			and tp.transit_pass_date is not null
			and (
				g.transit_pass_datetime is null
				or g.transit_pass_datetime = timestamp(g.transit_pass_date, '00:00:00')
			)
		"""
	)
