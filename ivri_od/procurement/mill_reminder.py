# Copyright (c) 2026, Profezzo and contributors
"""Monthly reminders shown as a banner at the top of the desk (for example the electricity bill and the EPF).

A Mill Reminder says: from which day of the month it shows, for how many days, and which roles see it. A user with one of those roles sees the
banner until someone marks it as completed for that month; it then goes from the desk for everybody, and comes back next month. Nothing has to
run in the background: the days that are active are worked out from today's date each time the desk asks.
"""

import calendar
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import getdate, today

FALLBACK_ROLE = "System Manager"  # who sees a reminder that has no roles yet


def start_of(year, month, day):
	"""The day the reminder starts in a month; a 31st becomes the last day of a shorter month."""
	return date(year, month, min(int(day), calendar.monthrange(year, month)[1]))


def active_window(day, visible_days, on):
	"""(period, start, end) when `on` falls in a month's window of the reminder, else None. A window can run into the next month, so the
	month before is checked too. The period (YYYY-MM) is the month in which the window starts."""
	on = getdate(on)
	for year, month in ((on.year, on.month), _previous_month(on)):
		start = start_of(year, month, day)
		end = start + timedelta(days=max(int(visible_days), 1) - 1)
		if start <= on <= end:
			return f"{year}-{month:02d}", start, end
	return None


def _previous_month(on):
	first = on.replace(day=1) - timedelta(days=1)
	return first.year, first.month


def allowed_roles(reminder):
	roles = {row.role for row in reminder.get("roles") or [] if row.role}
	return roles or {FALLBACK_ROLE}


def user_may_see(reminder, user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(allowed_roles(reminder) & set(frappe.get_roles(user)))


def is_completed(reminder_name, period):
	"""True when the reminder of that month has a completion that is not cancelled (a cancelled one makes it show again)."""
	return bool(frappe.db.exists("Mill Reminder Completion", {"reminder": reminder_name, "period": period, "docstatus": ["!=", 2]}))


@frappe.whitelist()
def get_active_reminders(on=None):
	"""The reminders the current user should see on the desk now."""
	if frappe.session.user == "Guest":
		return []
	on = getdate(on) if on else getdate(today())
	result = []
	for name in frappe.get_all("Mill Reminder", filters={"enabled": 1}, pluck="name"):
		reminder = frappe.get_doc("Mill Reminder", name)
		window = active_window(reminder.day_of_month, reminder.visible_for_days, on)
		if not window or not user_may_see(reminder) or is_completed(name, window[0]):
			continue
		period, start, end = window
		result.append(
			{
				"name": name,
				"title": reminder.reminder_title,
				"message": reminder.message,
				"period": period,
				"start": str(start),
				"end": str(end),
			}
		)
	return result


@frappe.whitelist()
def get_people():
	"""The active users to choose Approved By from (read by anybody who sees a reminder, so it does not need the User list). Entered By is not chosen: it is the person logged in."""
	if frappe.session.user == "Guest":
		return []
	return frappe.get_all(
		"User",
		filters={"enabled": 1, "name": ["not in", ["Administrator", "Guest"]], "user_type": "System User"},
		fields=["name as user", "full_name"],
		order_by="full_name asc",
		ignore_permissions=True,
	)


@frappe.whitelist()
def get_banks():
	"""The banks to choose from in the Mark as completed form: the Bank list of the desk (banks of India and the local banks of Odisha)."""
	if frappe.session.user == "Guest":
		return []
	return frappe.get_all("Bank", pluck="name", order_by="name asc", ignore_permissions=True)


@frappe.whitelist()
def mark_completed(reminder, period, bank=None, amount=None, entered_by=None, approved_by=None):
	"""Mark the reminder of a month as done, with the bank, the amount and who approved it. Entered By is always the person who is logged in (what the
	screen sends is ignored, so nobody can enter on another person's name). The completion is submitted, and the reminder then goes from the desk of
	everybody until next month."""
	doc = frappe.get_doc("Mill Reminder", reminder)
	if not user_may_see(doc):
		frappe.throw(_("You are not allowed to complete this reminder."), frappe.PermissionError)
	window = active_window(doc.day_of_month, doc.visible_for_days, today())
	if not window or window[0] != period:
		frappe.throw(_("This reminder is not active now."))
	if is_completed(reminder, period):
		return True
	completion = frappe.get_doc(
		{
			"doctype": "Mill Reminder Completion",
			"reminder": reminder,
			"period": period,
			"bank": bank,
			"amount": amount,
			"entered_by": frappe.session.user,
			"approved_by": approved_by,
		}
	)
	completion.flags.ignore_permissions = True
	completion.insert()
	completion.submit()
	return True
