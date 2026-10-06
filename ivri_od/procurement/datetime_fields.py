# Copyright (c) 2026, Profezzo and contributors

from __future__ import annotations

from frappe.utils import get_datetime, get_time, getdate, now_datetime


def combine_datetime(doc, dt_field: str, date_field: str | None = None, time_field: str | None = None):
	"""Resolve a Datetime from the primary field or legacy date + time."""
	value = doc.get(dt_field) if hasattr(doc, "get") else None
	if value:
		return get_datetime(value)
	if date_field and time_field:
		date_val = doc.get(date_field)
		time_val = doc.get(time_field)
		if date_val and time_val:
			return get_datetime(f"{date_val} {time_val}")
		if date_val:
			return get_datetime(f"{date_val} 00:00:00")
	return None


def split_datetime_to_date_time(dt_value, date_field: str, time_field: str, doc) -> None:
	if not dt_value:
		return
	dt = get_datetime(dt_value)
	doc.set(date_field, getdate(dt))
	doc.set(time_field, get_time(dt).replace(microsecond=0))


def ensure_doc_datetime(
	doc,
	dt_field: str,
	*,
	default_now: bool = False,
	date_field: str | None = None,
	time_field: str | None = None,
) -> object | None:
	"""Set primary datetime; optionally mirror into legacy date/time columns."""
	value = combine_datetime(doc, dt_field, date_field, time_field)
	if not value and default_now:
		value = now_datetime()
	if value:
		doc.set(dt_field, value)
	if date_field and time_field:
		split_datetime_to_date_time(value, date_field, time_field, doc)
	return value
