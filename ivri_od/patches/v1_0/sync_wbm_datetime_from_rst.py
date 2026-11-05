# Copyright (c) 2026, Profezzo and contributors
"""Weigh Bridge Measurement Date & Time = the Date & Time of its RST Details.

Weighments made from an RST showed the day they were created. This sets the RST Date & Time on every
existing one (and its measurement date and time). Safe to run again."""

import frappe
from frappe.utils import get_datetime, get_time, getdate


def execute():
	rst_rows = frappe.get_all("RST Details", fields=["name", "entry_datetime", "entry_date", "entry_time"])
	rst_time = {}
	for row in rst_rows:
		if row.entry_datetime:
			rst_time[row.name] = get_datetime(row.entry_datetime)
		elif row.entry_date:
			rst_time[row.name] = get_datetime(f"{row.entry_date} {row.entry_time or '00:00:00'}")

	for wbm in frappe.get_all(
		"Weigh Bridge Measurement",
		filters={"demo_rst_data": ["is", "set"]},
		fields=["name", "demo_rst_data", "date", "measurement_date", "measurement_time"],
	):
		value = rst_time.get(wbm.demo_rst_data)
		if not value:
			continue
		values = {
			"date": value,
			"measurement_date": getdate(value),
			"measurement_time": get_time(value).replace(microsecond=0),
		}
		if get_datetime(wbm.date) == value and wbm.measurement_date == values["measurement_date"]:
			continue
		frappe.db.set_value("Weigh Bridge Measurement", wbm.name, values, update_modified=False)
