# Copyright (c) 2026, Profezzo and contributors

import frappe


def execute():
	if not frappe.db.has_column("Weigh Bridge Measurement", "total_bags"):
		return

	frappe.db.sql(
		"""
		update `tabWeigh Bridge Measurement` w
		set total_bags = coalesce(
			(
				select sum(coalesce(d.jute_bags, 0) + coalesce(d.plastic_bags, 0))
				from `tabWeigh Bridge Bag Detail` d
				where d.parent = w.name
			),
			0
		)
		"""
	)
