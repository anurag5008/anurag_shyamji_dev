# Copyright (c) 2026, Profezzo and contributors

import json

import frappe
from frappe.tests import IntegrationTestCase

from ivri_od.procurement.report.dc_track import dc_track

MILL = "M999901"


class TestDCTrack(IntegrationTestCase):
	def setUp(self):
		self.records = {
			("DCRO", "View DC"): [
				({"Miller Code": MILL, "DC Code(RRC)": "DCF900001", "Generated Date": "05-01-2026", "RRC": "No_File", "FCI": "View_FCI"}, "12"),
				({"Miller Code": MILL, "DC Code(RRC)": "DCR900002", "Generated Date": "10-01-2026", "RRC": "View_RRC", "FCI": "No_File"}, "2"),
				({"Miller Code": MILL, "DC Code(RRC)": "DCR900003", "Generated Date": "12-01-2026"}, "3"),
				({"Miller Code": MILL, "DC Code(RRC)": "DCR900004", "Generated Date": "15-01-2026"}, "0"),
			],
			# FCI lots: one Transit Challan row per lot; lot 2 read twice counts once.
			("DCRO", "DC Transit Challan"): [
				({"DC Order No": "DCF900001", "Lot No.": "1", "Pending At": "Approved"}, None),
				({"DC Order No": "DCF900001", "Lot No.": "2", "Pending At": "Approved"}, None),
				({"DC Order No": "DCF900001", "Lot No.": "2", "Pending At": "Approved"}, None),
				({"DC Order No": "DCF900001", "Lot No.": "3", "Pending At": "Rejected"}, None),
			],
			# RRC lots: SCMS Lot Search; a DC not in View DC is still listed.
			("SCMS", "Lot Search"): [
				({"DC No.": "DCR900002", "Lot No.": "7", "Receipt Date": "20/01/2026", "Challan Status": "Accepted"}, None),
				({"DC No.": "DCR900002", "Lot No.": "8", "Receipt Date": "22/01/2026", "Challan Status": "Accepted"}, None),
				({"DC No.": "DCR900009", "Lot No.": "1", "Challan Status": "Accepted"}, None),
			],
		}
		# Files saved from the rows' buttons: (receipt_file, documents) by record name.
		self.files = {
			"View DC-0": ("/private/files/DCF900001.pdf", None),
			"DC Transit Challan-0": (None, {"Details": "/private/files/d1.pdf", "AC Note Doc": "/private/files/a1.pdf"}),
			"Lot Search-0": ("/private/files/lot7.pdf", None),
		}
		real = dc_track._records

		def fake_records(site, section, like=None):
			out = []
			for n, (cells, _lots) in enumerate(self.records.get((site, section), [])):
				if like and like not in json.dumps(cells):
					continue
				receipt, documents = self.files.get(f"{section}-{n}", (None, None))
				out.append(
					frappe._dict(
						name=f"{section}-{n}",
						row_data=json.dumps(cells),
						mill_id="",
						receipt_file=receipt,
						documents=json.dumps(documents) if documents else None,
					)
				)
			return out

		def fake_details(names):
			lots = {f"View DC-{n}": l for n, (_c, l) in enumerate(self.records[("DCRO", "View DC")])}
			return {name: [{"Lots": lots[name]}] for name in names if lots.get(name) is not None}

		dc_track._records = fake_records
		self._real_details = dc_track._get_details
		dc_track._get_details = fake_details
		self.addCleanup(setattr, dc_track, "_records", real)
		self.addCleanup(setattr, dc_track, "_get_details", self._real_details)

	def rows(self, **filters):
		return {r["dc_no"]: r for r in dc_track.execute(filters)[1]}

	def test_remaining_lots_and_status(self):
		rows = self.rows()
		fci = rows["DCF900001"]
		self.assertEqual((fci["total_lots"], fci["delivered_lots"], fci["remaining_lots"]), (12, 2, 10))
		self.assertEqual((fci["status"], fci["dc_type"], fci["not_counted"]), ("Partly Delivered", "FCI", 1))
		self.assertEqual(fci["mill_id"], MILL)
		self.assertEqual(fci["dc_date"], "2026-01-05")

		rrc = rows["DCR900002"]
		self.assertEqual((rrc["remaining_lots"], rrc["status"], rrc["dc_type"]), (0, "Fulfilled", "RRC"))
		self.assertEqual((rrc["delivered_lot_nos"], rrc["last_delivery"]), ("7, 8", "2026-01-22"))

		self.assertEqual(rows["DCR900003"]["status"], "Not Started")
		self.assertEqual(rows["DCR900004"]["status"], "No Lots on DC")
		self.assertEqual(rows["DCR900009"]["status"], "DC Not in View DC")

	def test_filters(self):
		self.assertEqual(set(self.rows(status="Fulfilled")), {"DCR900002"})
		self.assertEqual(set(self.rows(dc_type="FCI")), {"DCF900001"})
		self.assertEqual(set(self.rows(dc_no="dcr90000")), {"DCR900002", "DCR900003", "DCR900004", "DCR900009"})
		self.assertEqual(set(self.rows(from_date="2026-01-10", to_date="2026-01-12")), {"DCR900002", "DCR900003"})
		self.assertEqual(len(self.rows(mill_id=MILL.lower())), 4)

	def test_dc_note_and_delivered_lots_popup(self):
		rows = self.rows()
		self.assertEqual(rows["DCF900001"]["dc_note"], "/private/files/DCF900001.pdf")
		self.assertEqual(rows["DCR900002"]["dc_note"], "")

		# FCI: Transit Challan rows, counted as in Lots Delivered, with Details and Acknowledgement Note.
		fci = dc_track.get_delivered_lots("dcf900001")
		self.assertEqual((fci["dc_type"], fci["counted"], fci["dc_note"]), ("FCI", 2, "/private/files/DCF900001.pdf"))
		self.assertEqual(
			[(lot["lot_no"], lot["counted"]) for lot in fci["lots"]],
			[("1", "Counted"), ("2", "Counted"), ("2", "Read Twice"), ("3", "Rejected / Cancelled")],
		)
		self.assertEqual(fci["file_labels"], ["Details", "Acknowledgement Note"])
		self.assertEqual(
			fci["lots"][0]["files"],
			[
				{"label": "Details", "url": "/private/files/d1.pdf"},
				{"label": "Acknowledgement Note", "url": "/private/files/a1.pdf"},
			],
		)

		# RRC: Lot Search rows with the file saved from the row (Acknowledgement).
		rrc = dc_track.get_delivered_lots("DCR900002")
		self.assertEqual((rrc["dc_type"], rrc["counted"], rrc["file_labels"]), ("RRC", 2, ["Acknowledgement"]))
		self.assertEqual(rrc["lots"][0]["files"], [{"label": "Acknowledgement", "url": "/private/files/lot7.pdf"}])
		self.assertEqual(rrc["lots"][1]["files"], [])
