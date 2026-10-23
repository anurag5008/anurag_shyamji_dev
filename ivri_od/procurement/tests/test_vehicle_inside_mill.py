# Copyright (c) 2026, Profezzo and Contributors
# See license.txt
"""Vehicle tracking: Gate In -> Gate Exit -> re-entry.

Runs the real mill_gate SQL and the Gate Entry / Gate Exit hooks against an
in-memory SQLite copy of the two gate tables. No site, no MariaDB, no writes
to any real database.
"""

import sqlite3
import unittest
from unittest.mock import MagicMock, patch

import frappe

from ivri_od.procurement import mill_gate
from ivri_od.procurement.doctype.gate_entry.gate_entry import GateEntry
from ivri_od.procurement.doctype.gate_exit.gate_exit import GateExit


def _bare(cls, **values):
	"""Controller instance without Document.__init__ (which needs a site for meta)."""
	doc = cls.__new__(cls)
	doc.__dict__.update(values)
	return doc


class FakeDb:
	"""The few frappe.db calls used by mill_gate and the gate hooks."""

	def __init__(self):
		self.conn = sqlite3.connect(":memory:")
		self.conn.row_factory = sqlite3.Row
		self.conn.executescript(
			"""
			CREATE TABLE `tabGate Entry` (
				name TEXT PRIMARY KEY, in_out TEXT, vehicle_no TEXT, driver_name TEXT,
				gate_entry_in TEXT, inside_mill INTEGER DEFAULT 0, going_to_weighment INTEGER DEFAULT 0,
				entry_date TEXT, entry_time TEXT, creation TEXT);
			CREATE TABLE `tabGate Exit` (
				name TEXT PRIMARY KEY, vehicle_no TEXT, gate_entry_in TEXT);
			CREATE TABLE `tabQuality Check` (name TEXT PRIMARY KEY, gate_entry TEXT);
			"""
		)
		self.clock = 0

	@staticmethod
	def _table(doctype):
		return f"`tab{doctype}`"

	def _where(self, filters):
		clauses, values = [], []
		for key, value in (filters or {}).items():
			if isinstance(value, (list, tuple)):
				clauses.append(f"{key} != ?")
				values.append(value[1])
			else:
				clauses.append(f"{key} = ?")
				values.append(value)
		return " AND ".join(clauses) or "1=1", values

	def sql(self, query, values=(), as_dict=False, pluck=False):
		if not isinstance(values, (list, tuple)):
			values = (values,)
		rows = self.conn.execute(query.replace("%s", "?"), tuple(values)).fetchall()
		if pluck:
			return [row[0] for row in rows]
		if as_dict:
			return [frappe._dict(dict(row)) for row in rows]
		return [tuple(row) for row in rows]

	def exists(self, doctype, filters=None):
		if isinstance(filters, str):
			filters = {"name": filters}
		where, values = self._where(filters)
		row = self.conn.execute(
			f"SELECT name FROM {self._table(doctype)} WHERE {where} LIMIT 1", values
		).fetchone()
		return row[0] if row else None

	def get_value(self, doctype, filters, fieldname, as_dict=False):
		if isinstance(filters, str):
			filters = {"name": filters}
		fields = [fieldname] if isinstance(fieldname, str) else list(fieldname)
		where, values = self._where(filters)
		row = self.conn.execute(
			f"SELECT {', '.join(fields)} FROM {self._table(doctype)} WHERE {where} LIMIT 1", values
		).fetchone()
		if not row:
			return None
		if as_dict:
			return frappe._dict(dict(row))
		return row[0] if isinstance(fieldname, str) else tuple(row)

	def set_value(self, doctype, name, fieldname, value, update_modified=True):
		self.conn.execute(
			f"UPDATE {self._table(doctype)} SET {fieldname} = ? WHERE name = ?", (value, name)
		)

	def insert(self, table, **values):
		self.conn.execute(
			f"INSERT INTO `tab{table}` ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})",
			tuple(values.values()),
		)

	def flag(self, name):
		return self.conn.execute("SELECT inside_mill FROM `tabGate Entry` WHERE name = ?", (name,)).fetchone()[0]


class TestVehicleInsideMill(unittest.TestCase):
	def setUp(self):
		frappe.local.lang = "en"
		self.db = FakeDb()
		def throw(msg, exc=frappe.ValidationError, title=None, **kwargs):
			raise exc(msg)

		for target, value in (("db", self.db), ("msgprint", MagicMock()), ("throw", throw)):
			patcher = patch.object(frappe, target, value, create=True)
			patcher.start()
			self.addCleanup(patcher.stop)
		# GRN creation is covered in test_grn_after_gate_exit
		patcher = patch.object(GateExit, "_create_grn_notes")
		patcher.start()
		self.addCleanup(patcher.stop)
		self.n = 0

	def _gate_in(self, vehicle="OD01AB1234"):
		"""Gate Entry (In), saved through the real validate + insert flag logic."""
		self.n += 1
		doc = _bare(GateEntry, name=f"GE-{self.n}", in_out="In", vehicle_no=mill_gate.normalize_vehicle_no(vehicle))
		with patch.object(GateEntry, "is_new", return_value=True):
			doc._sync_inside_mill_flag()
			doc._validate_gate_in()
		self.db.insert(
			"Gate Entry",
			name=doc.name, in_out="In", vehicle_no=doc.vehicle_no, going_to_weighment=1,
			inside_mill=doc.inside_mill, entry_date="2026-10-23", entry_time=f"10:00:{self.n:02d}",
			creation=f"2026-10-23 10:00:{self.n:02d}",
		)
		return doc

	def _gate_exit(self, vehicle="OD01AB1234", gate_entry_in=""):
		self.n += 1
		doc = _bare(
			GateExit, name=f"GX-{self.n}", vehicle_no=vehicle, gate_entry_in=gate_entry_in,
			driver_name="", exit_datetime="2026-10-23 11:00:00",
		)
		doc.validate()
		self.db.insert("Gate Exit", name=doc.name, vehicle_no=doc.vehicle_no, gate_entry_in=doc.gate_entry_in)
		doc.on_update()
		return doc

	def _dropdowns(self, txt=""):
		return {
			"gate_exit": mill_gate.get_vehicles_inside_mill(txt),
			"weighment": mill_gate.get_weighment_vehicles_inside_mill(txt),
		}

	def test_gate_entry_sets_inside_mill_and_enters_dropdowns(self):
		ge = self._gate_in()
		self.assertEqual(self.db.flag(ge.name), 1)
		self.assertEqual(self._dropdowns()["gate_exit"], ["OD01AB1234"])
		self.assertEqual(self._dropdowns()["weighment"], ["OD01AB1234"])
		self.assertEqual(mill_gate.get_open_gate_entry_in_for_vehicle("od01ab1234 "), ge.name)

	def test_gate_exit_clears_flag_and_leaves_dropdowns(self):
		ge = self._gate_in()
		self._gate_exit(gate_entry_in=ge.name)
		self.assertEqual(self.db.flag(ge.name), 0)
		self.assertFalse(mill_gate.is_gate_in_inside_mill(ge.name))
		self.assertEqual(self._dropdowns(), {"gate_exit": [], "weighment": []})
		self.assertIsNone(mill_gate.get_open_gate_entry_in_for_vehicle("OD01AB1234"))

	def test_gate_exit_resolves_open_visit_without_explicit_link(self):
		ge = self._gate_in()
		gx = self._gate_exit()
		self.assertEqual(gx.gate_entry_in, ge.name)
		self.assertEqual(self.db.flag(ge.name), 0)

	def test_reentry_makes_vehicle_available_again_and_keeps_old_visit_closed(self):
		first = self._gate_in()
		self._gate_exit(gate_entry_in=first.name)
		second = self._gate_in()
		self.assertEqual(self.db.flag(first.name), 0)
		self.assertEqual(self.db.flag(second.name), 1)
		self.assertEqual(self._dropdowns()["gate_exit"], ["OD01AB1234"])
		self.assertEqual(self._dropdowns()["weighment"], ["OD01AB1234"])
		self.assertEqual(mill_gate.get_open_gate_entry_in_for_vehicle("OD01AB1234"), second.name)

	def test_quality_check_dropdown_follows_the_open_visit(self):
		from ivri_od.procurement.doctype.quality_check.quality_check import get_vehicle_no_autocomplete

		def vehicles():
			return [row["value"] for row in get_vehicle_no_autocomplete()]

		first = self._gate_in()
		self.assertEqual(vehicles(), ["OD01AB1234"])
		self._gate_exit(gate_entry_in=first.name)
		self.assertEqual(vehicles(), [])
		self._gate_in()
		self.assertEqual(vehicles(), ["OD01AB1234"])

	def test_second_gate_in_while_inside_is_blocked(self):
		self._gate_in()
		with self.assertRaises(frappe.ValidationError):
			self._gate_in()

	def test_second_gate_exit_for_same_visit_is_blocked(self):
		ge = self._gate_in()
		self._gate_exit(gate_entry_in=ge.name)
		with self.assertRaises(frappe.ValidationError):
			self._gate_exit(gate_entry_in=ge.name)

	def test_deleting_gate_exit_reopens_only_that_visit(self):
		first = self._gate_in()
		gx = self._gate_exit(gate_entry_in=first.name)
		self.db.conn.execute("DELETE FROM `tabGate Exit` WHERE name = ?", (gx.name,))
		gx.on_trash()
		self.assertEqual(self.db.flag(first.name), 1)

	def test_other_vehicles_are_not_affected(self):
		a = self._gate_in("OD01AB1234")
		b = self._gate_in("CG04XY9999")
		self._gate_exit("OD01AB1234", a.name)
		self.assertEqual(self.db.flag(b.name), 1)
		self.assertEqual(self._dropdowns()["gate_exit"], ["CG04XY9999"])
