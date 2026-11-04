# Copyright (c) 2026, Profezzo and contributors
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import frappe

from ivri_od.procurement import mill_reminder as mr

ROOT = Path(__file__).resolve().parents[2]


class Row(dict):
	def __getattr__(self, key):
		return self.get(key)


class FakeReminder(dict):
	def __getattr__(self, key):
		return self.get(key)


class TestWindow(unittest.TestCase):
	def test_a_reminder_shows_from_its_day_for_the_visible_days(self):
		for day, expected in ((1, None), (2, "2026-11"), (3, "2026-11"), (4, "2026-11"), (5, None)):
			window = mr.active_window(2, 3, date(2026, 11, day))
			self.assertEqual(window[0] if window else None, expected, day)
		self.assertEqual(mr.active_window(7, 3, date(2026, 11, 9))[1:], (date(2026, 11, 7), date(2026, 11, 9)))
		self.assertIsNone(mr.active_window(7, 3, date(2026, 11, 10)))

	def test_a_window_can_run_into_the_next_month(self):
		window = mr.active_window(30, 5, date(2026, 12, 2))
		self.assertEqual((window[0], window[1], window[2]), ("2026-11", date(2026, 11, 30), date(2026, 12, 4)))

	def test_the_31st_moves_to_the_last_day_of_a_short_month(self):
		self.assertEqual(mr.start_of(2026, 2, 31), date(2026, 2, 28))
		self.assertEqual(mr.start_of(2028, 2, 31), date(2028, 2, 29))
		self.assertEqual(mr.start_of(2026, 4, 31), date(2026, 4, 30))
		self.assertEqual(mr.start_of(2026, 12, 31), date(2026, 12, 31))

	def test_the_same_reminder_has_a_different_period_each_month(self):
		self.assertNotEqual(mr.active_window(2, 3, date(2026, 11, 2))[0], mr.active_window(2, 3, date(2026, 12, 2))[0])


class TestWhoSeesIt(unittest.TestCase):
	def test_only_the_chosen_roles_see_a_reminder(self):
		reminder = FakeReminder(roles=[Row(role="Accounts Manager"), Row(role="Purchase Manager")])
		with patch.object(frappe, "get_roles", return_value=["Accounts Manager", "All"]):
			self.assertTrue(mr.user_may_see(reminder, "a@x.com"))
		with patch.object(frappe, "get_roles", return_value=["Stock User", "All"]):
			self.assertFalse(mr.user_may_see(reminder, "b@x.com"))

	def test_without_roles_only_system_managers_see_it(self):
		reminder = FakeReminder(roles=[])
		with patch.object(frappe, "get_roles", return_value=["System Manager"]):
			self.assertTrue(mr.user_may_see(reminder, "a@x.com"))
		with patch.object(frappe, "get_roles", return_value=["Accounts Manager"]):
			self.assertFalse(mr.user_may_see(reminder, "b@x.com"))

	def test_the_administrator_always_sees_it(self):
		self.assertTrue(mr.user_may_see(FakeReminder(roles=[Row(role="Nobody")]), "Administrator"))


class TestFilesAndSeed(unittest.TestCase):
	def test_the_doctypes_banner_hook_and_seed_patch_are_in_place(self):
		for name in ("mill_reminder", "mill_reminder_role", "mill_reminder_completion"):
			data = json.loads((ROOT / "procurement" / "doctype" / name / f"{name}.json").read_text())
			self.assertEqual(data["module"], "Procurement")
		reminder = json.loads((ROOT / "procurement" / "doctype" / "mill_reminder" / "mill_reminder.json").read_text())
		fields = {f["fieldname"]: f for f in reminder["fields"]}
		self.assertEqual((fields["roles"]["fieldtype"], fields["roles"]["options"]), ("Table", "Mill Reminder Role"))
		self.assertIn("/assets/ivri_od/js/mill_reminder_banner.js", (ROOT / "hooks.py").read_text())
		self.assertIn("ivri_od.patches.v1_0.create_mill_reminders", (ROOT / "patches.txt").read_text())
		seed = (ROOT / "patches" / "v1_0" / "create_mill_reminders.py").read_text()
		self.assertIn('"Electricity Bill and EPF", 2, "Reminder: Please pay the electricity bill and the EPF."', seed)
		self.assertIn('"Raw Mill Electricity Bill", 7, "Reminder: Please pay the electricity bill of the Raw Mill."', seed)
		script = (ROOT / "public" / "js" / "mill_reminder_banner.js").read_text()
		for part in ("get_active_reminders", "mark_completed", "Mark as completed", "page-change", "page-desktop"):
			self.assertIn(part, script, part)


class TestAnimatedBanner(unittest.TestCase):
	def test_the_banner_is_a_luxury_dark_and_gold_panel_that_travels_across_the_screen(self):
		script = (ROOT / "public" / "js" / "mill_reminder_banner.js").read_text()
		for part in ("@keyframes ivri-rise", "@keyframes ivri-edge", "@keyframes ivri-sweep", "@keyframes ivri-breathe", "@keyframes ivri-ticker",
				"prefers-reduced-motion: reduce", "reminder_kanha.jpg", "padding-left: 100%", "translateX(-100%)", "animation-play-state: paused", "--ivri-duration",
				"mask-image: linear-gradient(90deg, transparent 0, #000 7%, #000 93%, transparent 100%)", "#080d22", "#d6b264", "#f6e8bf", "border-radius: 999px",
				"ivri-reminder-label", "Mark as completed"):
			self.assertIn(part, script, part)
		self.assertIn("mill_reminder_banner.js?v=", (ROOT / "hooks.py").read_text())

	def test_the_picture_of_kanha_is_a_small_square_with_a_credits_note(self):
		picture = ROOT / "public" / "images" / "reminder_kanha.jpg"
		self.assertTrue(picture.exists())
		self.assertLess(picture.stat().st_size, 80 * 1024)  # the banner loads on every desk page
		try:
			from PIL import Image
		except ImportError:  # the image library is not installed here
			return
		self.assertEqual(Image.open(picture).size, (240, 240))
		credits = (ROOT / "public" / "images" / "reminder_kanha_CREDITS.txt").read_text()
		for part in ("CC0", "commons.wikimedia.org", "Infinite Eyes", "2 November 2026"):
			self.assertIn(part, credits, part)
		self.assertFalse((ROOT / "public" / "images" / "reminder_krishna.svg").exists())  # the first drawing is no longer used


class TestCompletionDetails(unittest.TestCase):
	def _completion(self, **values):
		base = {"doctype": "Mill Reminder Completion", "reminder": "Electricity Bill and EPF", "period": "2026-11", "bank": "Example Bank", "amount": 15000, "entered_by": "a@x.com", "approved_by": "b@x.com"}
		base.update(values)
		doc = frappe.get_doc(base)
		doc.set("__islocal", True)  # a new document, as it is while insert() validates it
		return doc

	def _validate(self, doc, enabled=1):
		real = frappe.db.get_value  # only the User lookup is faked; Frappe reads its own settings through the same call
		people = {"a@x.com": "Anurag Singh", "b@x.com": "Rohit Sharma"}
		fake = lambda user: frappe._dict(enabled=enabled, full_name=people.get(user, ""))
		real_exists = frappe.db.exists
		banks = {"Example Bank", "HDFC Bank", "State Bank of India"}  # the Bank list, faked
		fake_exists = lambda *a, **k: (a[1] in banks) if a and a[0] == "Bank" else real_exists(*a, **k)
		with patch.object(frappe.db, "get_value", side_effect=lambda *a, **k: fake(a[1]) if a and a[0] == "User" else real(*a, **k)), patch.object(frappe.db, "exists", side_effect=fake_exists):
			doc.validate()

	def test_a_complete_form_passes_and_the_system_fills_the_date_time_and_login(self):
		doc = self._completion(completed_on="2000-01-01 00:00:00")
		self._validate(doc)
		self.assertNotEqual(str(doc.completed_on)[:10], "2000-01-01")  # whatever the screen sent, the system time is used
		self.assertEqual(doc.completed_by, frappe.session.user)

	def test_every_field_of_the_form_is_required(self):
		for field in ("bank", "entered_by", "approved_by"):
			with self.assertRaises(frappe.ValidationError, msg=field):
				self._validate(self._completion(**{field: ""}))
		for amount in (0, None, -5):
			with self.assertRaises(frappe.ValidationError, msg=amount):
				self._validate(self._completion(amount=amount))

	def test_the_people_must_be_active_users(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate(self._completion(), enabled=0)

	def test_the_completion_is_submittable_and_has_the_five_fields(self):
		data = json.loads((ROOT / "procurement" / "doctype" / "mill_reminder_completion" / "mill_reminder_completion.json").read_text())
		self.assertEqual(data["is_submittable"], 1)
		fields = {f["fieldname"]: f for f in data["fields"]}
		for name, label in (("completed_on", "Date and Time"), ("bank", "Bank"), ("amount", "Amount"), ("entered_by_name", "Entered By"), ("approved_by_name", "Approved By")):
			self.assertEqual(fields[name]["label"], label, name)  # the names are what the list and the form show
		self.assertEqual(fields["amount"]["fieldtype"], "Currency")
		self.assertEqual(fields["completed_on"]["fieldtype"], "Datetime")

	def test_a_cancelled_completion_does_not_hide_the_reminder(self):
		import inspect

		self.assertIn('"docstatus": ["!=", 2]', inspect.getsource(mr.is_completed))

	def test_the_screen_asks_for_the_details_before_submitting(self):
		script = (ROOT / "public" / "js" / "mill_reminder_banner.js").read_text()
		for part in ("frappe.ui.Dialog", '"Date and Time"', '"Bank"', '"Amount"', '"Entered By"', '"Approved By"', "primary_action_label: __(\"Submit\")", "get_people", "ask_details(reminder)", "now_datetime()"):
			self.assertIn(part, script, part)


class TestEnteredByIsLocked(unittest.TestCase):
	def test_the_screen_shows_the_logged_in_person_read_only_and_does_not_list_everybody(self):
		script = (ROOT / "public" / "js" / "mill_reminder_banner.js").read_text()
		line = [l for l in script.split("\n") if 'fieldname: "entered_by"' in l][0]
		self.assertIn('fieldtype: "Data"', line)
		self.assertIn("read_only: 1", line)
		self.assertIn("default: me", line)
		self.assertNotIn("options", line)  # no list of users on this field
		self.assertIn("frappe.session.user_fullname", script)
		self.assertIn("entered_by: frappe.session.user", script)
		self.assertIn('fieldname: "approved_by", fieldtype: "Select"', script)  # Approved By keeps its choice

	def test_the_server_always_uses_the_person_logged_in_as_entered_by(self):
		import inspect

		source = inspect.getsource(mr.mark_completed)
		self.assertIn('"entered_by": frappe.session.user', source)
		self.assertNotIn('"entered_by": entered_by', source)


class TestWhoCanSeeAndCancelTheRecords(unittest.TestCase):
	def test_a_system_manager_can_read_export_and_cancel_but_not_edit_or_delete(self):
		data = json.loads((ROOT / "procurement" / "doctype" / "mill_reminder_completion" / "mill_reminder_completion.json").read_text())
		perms = {p["role"]: p for p in data["permissions"]}
		manager = perms["System Manager"]
		for right in ("read", "report", "export", "print", "cancel"):
			self.assertEqual(manager.get(right), 1, right)
		for right in ("write", "create", "delete", "submit"):
			self.assertFalse(manager.get(right), right)  # the records are made only by the Mark as completed form


class TestNamesInTheList(unittest.TestCase):
	def test_the_validation_fills_the_names_the_client_knows(self):
		doc = TestCompletionDetails()._completion()
		TestCompletionDetails()._validate(doc)
		self.assertEqual((doc.entered_by_name, doc.approved_by_name), ("Anurag Singh", "Rohit Sharma"))

	def test_the_list_shows_names_and_keeps_the_logins_inside_the_record(self):
		data = json.loads((ROOT / "procurement" / "doctype" / "mill_reminder_completion" / "mill_reminder_completion.json").read_text())
		fields = {f["fieldname"]: f for f in data["fields"]}
		for name, label, source in (("entered_by_name", "Entered By", "entered_by.full_name"), ("approved_by_name", "Approved By", "approved_by.full_name")):
			self.assertEqual((fields[name]["label"], fields[name]["fetch_from"], fields[name]["in_list_view"]), (label, source, 1), name)
			self.assertEqual(fields[name]["read_only"], 1)
		for name in ("entered_by", "approved_by"):
			self.assertFalse(fields[name].get("in_list_view"), name)  # the email-like login is not in the list
			self.assertIn("(Login)", fields[name]["label"])
		order = data["field_order"]
		self.assertEqual(order[order.index("entered_by") + 1], "entered_by_name")
		self.assertEqual(order[order.index("approved_by") + 1], "approved_by_name")


class TestEarlierRecordsGetNames(unittest.TestCase):
	def test_a_patch_fills_the_names_of_records_made_before_the_name_fields_existed(self):
		source = (ROOT / "patches" / "v1_0" / "fill_completion_names.py").read_text()
		self.assertIn("entered_by_name", source)
		self.assertIn("approved_by_name", source)
		self.assertIn("update_modified=False", source)
		self.assertIn("ivri_od.patches.v1_0.fill_completion_names", (ROOT / "patches.txt").read_text())


class TestBankList(unittest.TestCase):
	def test_the_list_has_the_banks_of_india_and_the_local_banks_of_odisha(self):
		from ivri_od.procurement import bank_list as bl

		banks = bl.all_banks()
		self.assertEqual(len(banks), len(set(banks)))  # each bank once
		self.assertGreaterEqual(len(banks), 100)
		for name in ("State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank", "Punjab National Bank", "Bank of Baroda", "Canara Bank", "Union Bank of India",
				"Kotak Mahindra Bank", "IDBI Bank", "Yes Bank", "Federal Bank", "AU Small Finance Bank", "India Post Payments Bank"):
			self.assertIn(name, banks, name)
		odisha = bl.ODISHA
		self.assertIn("Odisha Grameen Bank", odisha)
		self.assertIn("Odisha State Co-operative Bank (OSCB)", odisha)
		self.assertEqual(len([b for b in odisha if "Central Co-operative Bank" in b]), 17)  # the 17 district central banks of Odisha
		for district in ("Cuttack", "Khordha", "Sambalpur", "Balasore-Bhadrak", "Berhampur", "United Puri-Nimapara"):
			self.assertIn(f"{district} Central Co-operative Bank (Odisha)", banks, district)
		self.assertEqual(len(bl.PUBLIC_SECTOR), 12)
		self.assertEqual(len(bl.PRIVATE_SECTOR), 21)
		self.assertIn("Compiled on 2 November 2026", bl.__doc__)
		self.assertIn("odishascb.bank.in", bl.__doc__)

	def test_a_bank_that_is_not_in_the_list_is_refused(self):
		doc = TestCompletionDetails()._completion(bank="Some Unknown Bank")
		with self.assertRaises(frappe.ValidationError):
			TestCompletionDetails()._validate(doc)
		TestCompletionDetails()._validate(TestCompletionDetails()._completion(bank="State Bank of India"))

	def test_the_screen_offers_a_type_to_search_bank_field_filled_from_the_bank_list(self):
		script = (ROOT / "public" / "js" / "mill_reminder_banner.js").read_text()
		for part in ('fieldtype: "Autocomplete", options: banks', "get_banks", "banks.includes(values.bank)"):
			self.assertIn(part, script, part)
		self.assertIn("ivri_od.patches.v1_0.add_indian_banks", (ROOT / "patches.txt").read_text())


class TestOnlyOnTheDesktopPage(unittest.TestCase):
	def test_the_banner_is_placed_inside_the_desktop_page_that_opens_at_desk(self):
		script = (ROOT / "public" / "js" / "mill_reminder_banner.js").read_text()
		for part in ('const PAGE = "page-desktop"', '$("#" + PAGE).prepend(box)', "function on_desktop_page()", '$("#" + PAGE).is(":visible")', "if (!on_desktop_page()) return"):
			self.assertIn(part, script, part)
		for gone in ("page-Workspaces", "ivri_od_landing_workspace", "sessionStorage", '$("body").prepend', "header.navbar", "proto.show"):
			self.assertNotIn(gone, script, gone)  # no workspace logic: the Desktop is the only page

	def test_the_desktop_page_of_this_frappe_version_is_called_desktop(self):
		desk = Path(frappe.__file__).resolve().parent / "desk" / "page" / "desktop" / "desktop.js"
		self.assertIn('frappe.pages["desktop"].on_page_load', desk.read_text())  # the page the banner sits in
