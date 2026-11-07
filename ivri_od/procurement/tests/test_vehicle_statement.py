# Copyright (c) 2026, Profezzo and contributors
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from ivri_od.procurement import vehicle_statement as vs

ROOT = Path(__file__).resolve().parents[2]


class TestVehicleRows(unittest.TestCase):
	def test_a_vehicle_that_comes_many_times_is_one_row_with_its_quantities_added(self):
		passes = [
			{"vehicle_no": "OD03Z2980", "quantity": 250.5}, {"vehicle_no": "od03z2980 ", "quantity": 300.25},  # the same vehicle written another way
			{"vehicle_no": "CG04HT3302", "quantity": 302.04}, {"vehicle_no": "OD 03 Z 2980", "quantity": 100},
		]
		rows = vs.vehicle_rows(passes)
		self.assertEqual([(r["vehicle_no"], r["trips"], r["qty"]) for r in rows], [("CG04HT3302", 1, 302.04), ("OD03Z2980", 3, 650.75)])

	def test_one_row_for_each_vehicle_and_ppc_with_bags_and_quantity_added(self):
		passes = [
			{"vehicle_no": "AP39UL7767", "ppc": "GHASIAN(S1051002)", "bags": 626, "quantity": 239.39},
			{"vehicle_no": "AP39UL7767", "ppc": "GHUNESH(S1051403)", "bags": 469, "quantity": 202.4},
			{"vehicle_no": "ap39 ul7767", "ppc": "GHASIAN(S1051002)", "bags": 550, "quantity": 233.52},
		]
		rows = vs.vehicle_rows(passes)
		self.assertEqual([(r["vehicle_no"], r["ppc"], r["trips"], r["bags"], r["qty"]) for r in rows],
			[("AP39UL7767", "GHASIAN(S1051002)", 2, 1176, 472.91), ("AP39UL7767", "GHUNESH(S1051403)", 1, 469, 202.4)])

	def test_the_rows_are_in_vehicle_number_order_like_the_clients_sheet(self):
		rows = vs.vehicle_rows([{"vehicle_no": n, "quantity": 1} for n in ("CG04JD4351", "AP39UL7767", "CG04HT3302", "CG04JC2725")])
		self.assertEqual([r["vehicle_no"] for r in rows], ["AP39UL7767", "CG04HT3302", "CG04JC2725", "CG04JD4351"])

	def test_a_vehicle_is_hired_unless_it_is_in_the_own_vehicle_list(self):
		rows = vs.vehicle_rows([{"vehicle_no": "OD03Z2980", "quantity": 1}, {"vehicle_no": "CG04HT3302", "quantity": 1}], own_vehicles=["od 03 z 2980"])
		self.assertEqual({r["vehicle_no"]: r["vehicle_type"] for r in rows}, {"OD03Z2980": "Own Vehicle", "CG04HT3302": "Hired Vehicle"})
		self.assertEqual(vs.vehicle_rows([{"vehicle_no": "X1", "quantity": 1}])[0]["vehicle_type"], "Hired Vehicle")  # an empty list: all hired

	def test_a_pass_without_a_vehicle_number_is_left_out(self):
		self.assertEqual(vs.vehicle_rows([{"vehicle_no": "", "quantity": 5}, {"vehicle_no": None, "quantity": 5}]), [])


class TestAmountAndVouchers(unittest.TestCase):
	def test_the_amount_is_quantity_times_rate_to_the_nearest_rupee(self):
		# from the client's sheet (Quantity x Rate): 239.39 x 53 = 12687.67 gave 12688, 202.4 x 40 gave 8096, 233.52 x 53 gave 12377;
		# the KM (48, 21 ...) is only noted. The amounts are whole rupees.
		self.assertEqual(vs.amount_of(239.39, 53), 12688.0)
		self.assertEqual(vs.amount_of(202.4, 40), 8096.0)
		self.assertEqual(vs.amount_of(233.52, 53), 12377.0)
		self.assertEqual(vs.amount_of(228.74, 53), 12123.0)
		self.assertEqual(vs.amount_of(212.82, 37), 7874.0)
		self.assertEqual(vs.amount_of(10, 0.05), 1.0)  # half a rupee goes up
		self.assertEqual(vs.amount_of(0, 40), 0)

	def test_voucher_numbers_follow_the_clients_sheet(self):
		# the sheet: 33161 -> 1, 11190 -> 2, 68335 -> 3,4, 79922 -> 5,6, 16417 -> 7
		amounts = [33161, 11190, 68335, 79922, 16417]
		self.assertEqual(vs.assign_vouchers(amounts), ["1", "2", "3,4", "5,6", "7"])
		# and further down the sheet: 98303 -> 14,15 and then 16,17 for 96975
		self.assertEqual(vs.assign_vouchers([98303, 96975], start=14), ["14,15", "16,17"])

	def test_the_limit_is_fifty_thousand(self):
		self.assertEqual([vs.vouchers_needed(a) for a in (0, 1, 50000, 50000.01, 100000, 100000.01, 150001)], [0, 1, 1, 2, 2, 3, 4])

	def test_a_row_without_an_amount_gets_no_voucher_and_does_not_use_a_number(self):
		self.assertEqual(vs.assign_vouchers([30000, 0, 60000]), ["1", "", "2,3"])

	def test_the_numbers_start_at_one(self):
		self.assertEqual(vs.assign_vouchers([10]), ["1"])


class TestNamesAndTitle(unittest.TestCase):
	def test_the_code_in_brackets_is_taken_from_a_ppas_name(self):
		self.assertEqual(vs.code_of("GAMBHARI(S1050406)"), "S1050406")
		self.assertEqual(vs.code_of("TUREKELA SCS LTD(S1051406)"), "S1051406")
		self.assertEqual(vs.code_of("NO CODE"), "")
		self.assertEqual(vs.code_of(None), "")

	def test_the_kms_title_is_made_from_the_season(self):
		self.assertEqual(vs.kms_title("Kharif(2025)"), "KMS 2025-26")  # the client's sheet: "KMS 2024-25", no crop in brackets
		self.assertEqual(vs.kms_title("Rabi(2025)"), "RMS 2025-26")  # the Rabi Marketing Season
		self.assertEqual(vs.kms_title("Kharif 2024"), "KMS 2024-25")
		self.assertEqual(vs.kms_title("Kharif(2099)"), "KMS 2099-00")
		self.assertEqual(vs.kms_title("something else"), "something else")


class TestDistrictFilter(unittest.TestCase):
	PASSES = [
		{"vehicle_no": "A1", "quantity": 10, "ppc": "ONE(S1)", "x": None},
		{"vehicle_no": "B2", "quantity": 20, "ppc": "TWO(S2)", "x": None},
		{"vehicle_no": "C3", "quantity": 30, "ppc": "THREE(S3)", "x": None},
		{"vehicle_no": "D4", "quantity": 40, "ppc": "NO BRACKETS", "x": None},
	]

	def _get(self, district, codes):
		def fake_get_all(doctype, **kw):
			if doctype == "PPAS Transit Pass":
				return [dict(p) for p in self.PASSES]
			if doctype == "PPC Master":
				return list(codes)
		with patch.object(frappe, "get_all", side_effect=fake_get_all):
			return vs.get_passes("M", "Kharif(2025)", district=district)

	def test_without_a_district_all_the_passes_are_used(self):
		self.assertEqual(len(self._get(None, [])), 4)

	def test_with_a_district_only_the_passes_of_its_ppcs_are_used(self):
		self.assertEqual([p["vehicle_no"] for p in self._get("Balangir", ["S1", "S3"])], ["A1", "C3"])

	def test_a_district_with_no_ppc_in_the_master_is_refused_with_a_clear_message(self):
		with self.assertRaises(frappe.ValidationError):
			self._get("Nowhere", [])


class TestDocumentCalculation(unittest.TestCase):
	def _doc(self, rows):
		doc = frappe.new_doc("Vehicle Wise Statement")
		doc.miller, doc.season = "M", "Kharif(2025)"
		for vehicle, ppc, qty, km, rate in rows:
			doc.append("items", {"vehicle_no": vehicle, "ppc": ppc, "bags": 100, "qty": qty, "km": km, "rate": rate})
		return doc

	def test_the_document_numbers_the_vehicles_works_out_amounts_vouchers_and_totals(self):
		doc = self._doc([
			("AP39UL7767", "GHASIAN(S1051002)", 472.91, 48, 53), ("AP39UL7767", "GHUNESH(S1051403)", 202.4, 21, 40),
			("CG04HT3302", "DHAMANDANGA(S1051401)", 149.51, 8, 32), ("CG04HT3302", "DHOLMANDAL(S1051411)", 152.53, 25, 42),
			("CG04JC2725", "TUREKELA(S1051406)", 212.82, 15, 37), ("CG04JC2725", "CHULIFUNKA(S1050308)", 220.75, 27, 43),
		])
		with patch.object(vs, "own_vehicle_numbers", return_value=["cg04ht3302"]):
			doc.recalculate()
		rows = doc.items
		# hired vehicles first (each with its PPC rows together), the own vehicle CG04HT3302 last: no S.L No, voucher or payment mode
		self.assertEqual([r.vehicle_no for r in rows], ["AP39UL7767", "AP39UL7767", "CG04JC2725", "CG04JC2725", "CG04HT3302", "CG04HT3302"])
		self.assertEqual([r.amount for r in rows], [25064, 8096, 7874, 9492, 4784, 6406])  # qty x rate; the sheet's 11190 for CG04HT3302
		self.assertEqual([r.sl_no for r in rows], ["1", "", "2", "", "", ""])
		self.assertEqual([r.voucher_no for r in rows], ["1", "", "2", "", "", ""])  # by the vehicle's total: 33160 and 17366
		self.assertEqual([r.payment_mode for r in rows], ["CASH", "CASH", "CASH", "CASH", "", ""])
		self.assertEqual({r.vehicle_type for r in rows[:4]}, {"Hired Vehicle"})
		self.assertEqual({r.vehicle_type for r in rows[4:]}, {"Own Vehicle"})
		self.assertEqual((doc.total_vehicles, doc.total_vouchers), (3, 2))
		self.assertEqual((doc.hired_qty, doc.hired_amount), (1108.88, 50526))
		self.assertEqual((doc.own_qty, doc.own_amount), (302.04, 11190))
		self.assertEqual((doc.total_qty, doc.total_amount), (1410.92, 61716))
		self.assertEqual(doc.kms_title, "KMS 2025-26")

	def test_the_vouchers_follow_the_total_of_the_vehicle_not_of_one_ppc_row(self):
		doc = self._doc([("OD01A0001", "P1(1)", 600, 10, 50), ("OD01A0001", "P2(2)", 600, 10, 50), ("OD02B0002", "P1(1)", 10, 10, 50)])
		with patch.object(vs, "own_vehicle_numbers", return_value=[]):
			doc.recalculate()
		self.assertEqual([r.amount for r in doc.items], [30000, 30000, 500])  # 60000 is two vouchers (each row alone would be one)
		self.assertEqual([r.voucher_no for r in doc.items], ["1,2", "", "3"])
		lines = vs.vehicle_lines(doc)
		self.assertEqual([(l.vehicle_no, l.sl_no, l.qty, l.amount, l.voucher_no) for l in lines], [("OD01A0001", 1, 1200.0, 60000.0, "1,2"), ("OD02B0002", 2, 10.0, 500.0, "3")])
		self.assertEqual([(v["voucher_no"], v["vehicle_no"], v["amount"]) for v in vs.debit_vouchers(doc)], [("1", "OD01A0001", 30000), ("2", "OD01A0001", 30000), ("3", "OD02B0002", 500)])


class TestFilesAndPrint(unittest.TestCase):
	def test_the_documents_the_script_and_the_print_are_in_place(self):
		base = ROOT / "procurement" / "doctype"
		statement = json.loads((base / "vehicle_wise_statement" / "vehicle_wise_statement.json").read_text())
		fields = {f["fieldname"]: f for f in statement["fields"]}
		self.assertEqual((fields["district"]["options"], fields["items"]["options"]), ("District Master", "Vehicle Wise Statement Item"))
		for name in ("miller", "season"):
			self.assertEqual((fields[name]["fieldtype"], fields[name]["reqd"]), ("Select", 1))
		item = {f["fieldname"]: f for f in json.loads((base / "vehicle_wise_statement_item" / "vehicle_wise_statement_item.json").read_text())["fields"]}
		for name, label in (("sl_no", "S.L No"), ("vehicle_no", "Vehicle No"), ("qty", "Qty in Qntls"), ("km", "KM"), ("rate", "Rate"), ("amount", "Amount in Rs"), ("voucher_no", "Voucher No"), ("payment_mode", "Payment Mode"), ("vehicle_type", "Vehicle Type")):
			self.assertEqual(item[name]["label"], label, name)
		for name in ("sl_no", "vehicle_no", "qty", "amount", "voucher_no", "payment_mode", "vehicle_type"):
			self.assertEqual(item[name]["read_only"], 1, name)  # worked out or fetched, not typed
		for name in ("km", "rate"):
			self.assertFalse(item[name].get("read_only"), name)
		self.assertTrue((base / "own_vehicle" / "own_vehicle.json").exists())
		script = (base / "vehicle_wise_statement" / "vehicle_wise_statement.js").read_text()
		for part in ("get_filter_options", "Fetch Details", "fetch_details", "VOUCHER_LIMIT = 50000", "Math.ceil(amount / VOUCHER_LIMIT)"):
			self.assertIn(part, script, part)
		html = {d["name"]: d["html"] for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		for part in ("VEHICLE WISE STATEMENT OF", "PADDY LIFTED", "CMR DELIVERY (", "FOR {{ doc.kms_title or doc.season }}", "ALONG WITH VOUCHER DETAILS", "S.L NO", "VEHICLE NO.", "QUANTITY IN QUINTALS", "AMOUNT IN RS", "VOUCHER NO", "PAYMENT<br>MODE", "VEHICLE TYPE", "HIRED VEHICLE", "A/C)", "TOTAL"):
			self.assertIn(part, html, part)  # the corrected spelling
		self.assertIn("Vehicle Wise Statement - Shyamji", (ROOT / "hooks.py").read_text())


class TestNoDateFields(unittest.TestCase):
	def test_the_two_transit_pass_date_fields_are_gone_everywhere(self):
		base = ROOT / "procurement"
		for path in ("doctype/vehicle_wise_statement/vehicle_wise_statement.json", "doctype/vehicle_wise_statement/vehicle_wise_statement.py", "doctype/vehicle_wise_statement/vehicle_wise_statement.js", "vehicle_statement.py"):
			text = (base / path).read_text()
			for gone in ("from_date", "to_date", "Transit Pass Date From", "Transit Pass Date To"):
				self.assertNotIn(gone, text, f"{path}: {gone}")
		html = {d["name"]: d["html"] for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		self.assertNotIn("from_date", html)
		self.assertNotIn("to_date", html)
		fields = [f["fieldname"] for f in json.loads((base / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.json").read_text())["fields"]]
		self.assertEqual(fields[:7], ["naming_series", "statement_type", "cmr_to", "filters_section", "miller", "season", "column_break_1"])
		self.assertIn("district", fields)


class TestSheetFormat(unittest.TestCase):
	def test_the_row_number_column_is_hidden_and_a_print_pdf_button_is_added(self):
		script = (ROOT / "procurement" / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.js").read_text()
		for part in (".ivri-no-row-number .row-index { display: none !important; }", 'addClass("ivri-no-row-number")', '__("Print PDF")', "download_pdf", "no_letterhead: 1"):
			self.assertIn(part, script, part)

	def test_the_print_field_exists(self):
		fields = {f["fieldname"]: f for f in json.loads((ROOT / "procurement" / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.json").read_text())["fields"]}
		self.assertNotIn("account_name", fields)  # removed at the client's request: the A/C is always the District
		self.assertEqual(fields["mill_name_and_place"]["label"], "Mill Name and Place (for the print)")

	def test_the_sheet_has_the_clients_alignment_and_number_style(self):
		pf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		html, css = pf["html"], pf["css"]
		self.assertIn("""<td class="{{ 'c' if bal else 'l' }}">{{ row.vehicle_no }}</td>""", html)  # vehicle left (centred for Balangir)
		self.assertIn('rstrip("0").rstrip(".")', html)  # 532.5, 321, 300.75: no trailing zeros on the quantity
		self.assertIn('"%.2f" | format(row.amount or 0)', html)  # 62835.00: two decimals on the amount
		self.assertIn("td.r { text-align: right; }", css)
		self.assertIn("width: 94%", css)


class TestBalangirSheet(unittest.TestCase):
	def test_balangir_has_its_own_layout_and_other_districts_keep_the_first(self):
		html = {d["name"]: d["html"] for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		self.assertIn('(doc.district or "") | trim | lower == "balangir"', html)
		self.assertIn("(KHARIF)", html)
		self.assertIn("ALONG WITH VOUCHER DETAILS", html)
		self.assertIn('{%- if not bal %}', html)
		self.assertIn("A/C)", html)  # the other layout is still there


class TestPrintPages(unittest.TestCase):
	def test_rows_are_cut_into_whole_pages_and_the_title_is_centred(self):
		pf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		html, css = pf["html"], pf["css"]
		self.assertIn("first_page", html)
		self.assertIn("{%- if loop.first %}", html)  # title and column heads only once, on the first page  # the rows are counted per A4 page here, so no row is split by the PDF maker
		self.assertIn("vws-break", html)
		self.assertIn("page-break-after: always", css)
		self.assertIn("page-break-inside: avoid", css)
		self.assertIn("table-layout: fixed", css)
		self.assertIn(".vws .title", css)
		self.assertIn("text-align: center", css)
		self.assertIn("{%- if loop.last %}", html)  # TOTAL only on the last page


class TestBoldHeaders(unittest.TestCase):
	def test_title_and_column_heads_are_bold(self):
		pf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		self.assertIn("<th><b>VEHICLE NO.</b></th>", pf["html"])
		self.assertIn('class="title"><b>VEHICLE WISE STATEMENT', pf["html"])
		self.assertIn(".vws th, .vws th b { font-weight: 700 !important; }", pf["css"])


class TestDebitVoucher(unittest.TestCase):
	def test_words(self):
		self.assertEqual(vs.rupees_in_words(11191), "Eleven Thousand One Hundred And Ninety One Only")
		self.assertEqual(vs.rupees_in_words(33160), "Thirty Three Thousand One Hundred And Sixty Only")

	def test_an_amount_is_shared_equally_by_its_vouchers(self):
		self.assertEqual(vs.voucher_amounts(114300, 3), [38100, 38100, 38100])
		self.assertEqual(vs.voucher_amounts(60000, 2), [30000, 30000])
		self.assertEqual(vs.voucher_amounts(160000, 4), [40000] * 4)
		self.assertEqual(vs.voucher_amounts(100001, 3), [33333, 33333, 33335])  # the rupees left over go to the last voucher
		self.assertEqual(vs.voucher_amounts(50000, 1), [50000])
		self.assertEqual(vs.voucher_amounts(7570, 1), [7570])
		self.assertEqual(vs.voucher_amounts(0, 0), [])

	def test_one_voucher_for_every_voucher_number_in_number_order(self):
		doc = frappe._dict(items=[
			frappe._dict(vehicle_no="OD02CL7021", amount=114300, voucher_no="2,3,4", payment_mode="CASH"),
			frappe._dict(vehicle_no="CG04HT3302", amount=11191, voucher_no="1", payment_mode="CASH"),
			frappe._dict(vehicle_no="OD00X0000", amount=0, voucher_no="", payment_mode="CASH"),
		])
		got = vs.debit_vouchers(doc)
		self.assertEqual([(v["voucher_no"], v["vehicle_no"], v["amount"]) for v in got],
			[("1", "CG04HT3302", 11191), ("2", "OD02CL7021", 38100), ("3", "OD02CL7021", 38100), ("4", "OD02CL7021", 38100)])
		self.assertEqual(sum(v["amount"] for v in got[1:]), 114300)

	def test_format_button_and_hook(self):
		pf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Debit Voucher - Shyamji"]
		for part in ("DEBIT VOUCHER", "M/s SHREE SHYAMJI PADDY PROCESSING PVT LTD", "At/Po", "Paddy Transportation Charges from PPC to Mill.", "ACCOUNT)", ">Receiver<", ">Signature<"):
			self.assertIn(part, pf["html"], part)
		for stamped in ("Shree Shyamji Paddy Processing Pvt. Ltd.", "Authorised Person", "Director"):
			self.assertNotIn(stamped, pf["html"], stamped)  # these are the company's rubber stamp, not printed
		self.assertIn("Debit Voucher - Shyamji", (ROOT / "hooks.py").read_text())
		self.assertIn("ivri_od.procurement.vehicle_statement.debit_vouchers", (ROOT / "hooks.py").read_text())
		script = (ROOT / "procurement" / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.js").read_text()
		for part in ('__("Print PDF")', '__("Vehicle Statement")', '__("Debit Voucher")'):
			self.assertIn(part, script, part)

	def test_date_comes_from_the_start_date_tick_is_above_cash_and_there_is_room_to_sign(self):
		pf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Debit Voucher - Shyamji"]
		self.assertIn("v.date", pf["html"])  # the date comes from the start date asked on the button
		self.assertNotIn("Cash &#10003;", pf["html"])  # the tick is not beside the word in the blank
		self.assertIn('<span class="tick">&#10003;</span>{% endif %}Cash</span>/Cheque No.', pf["html"])  # tick above Cash in "Cash/Cheque No."
		self.assertIn("sign-space", pf["html"])
		self.assertIn(".dv .sign-space { height: 28mm; }", pf["css"])
		script = (ROOT / "procurement" / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.js").read_text()
		self.assertIn("frappe.prompt", script)
		self.assertIn("voucher_date", script)
		self.assertIn("per_date", script)


class TestStatementType(unittest.TestCase):
	def test_paddy_and_cmr(self):
		d = json.loads((ROOT / "procurement" / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.json").read_text())
		fields = {f["fieldname"]: f for f in d["fields"]}
		self.assertEqual((fields["statement_type"]["options"], fields["statement_type"]["default"]), ("Paddy\nCMR", "Paddy"))
		self.assertEqual(d["field_order"][:3], ["naming_series", "statement_type", "cmr_to"])
		self.assertEqual(fields["cmr_to"]["options"], "\nFCI\nRRC")
		self.assertEqual(fields["cmr_to"]["mandatory_depends_on"], 'eval:doc.statement_type=="CMR"')
		self.assertNotIn("depends_on", fields["district"])  # the district is used by Paddy (PPCs) and by the CMR print heading
		self.assertEqual((fields["miller"]["reqd"], fields["season"]["reqd"]), (1, 1))

	def test_cmr_needs_fci_or_rrc(self):
		from ivri_od.procurement.doctype.vehicle_wise_statement.vehicle_wise_statement import VehicleWiseStatement

		doc = frappe.new_doc("Vehicle Wise Statement")
		doc.statement_type = "CMR"
		with self.assertRaises(frappe.ValidationError):
			VehicleWiseStatement.check_statement_type(doc)
		doc.cmr_to = "FCI"
		doc.check_statement_type()
		doc.statement_type = ""
		doc.check_statement_type()
		self.assertEqual(doc.statement_type, "Paddy")


class TestLotSearchVehicle(unittest.TestCase):
	"""Lot Search from SCMS: the Vehicle No is read from the lot's PDF (Vehicle Registration No.)."""

	TEXT = (
		"12. VEHICLE DETAILS\nSl# Challan No. Vehicle Registration No. Driver Name Driver Aadhaar Date No of Bag.\n"
		"1 0038 OD03AB4135 NARENDRA KAANR XXXXXXXX6375 29-09-2026 580\n15. RESULT OF ANALYSIS/RE-ANALYSIS\nSl# 1 Broken 15.00"
	)

	def test_one_vehicle(self):
		from ivri_od.procurement.portal_sync import _vehicles_in

		self.assertEqual(_vehicles_in(self.TEXT), "OD03AB4135")

	def test_two_vehicles_and_spaces(self):
		from ivri_od.procurement.portal_sync import _vehicles_in

		text = self.TEXT.replace("15. RESULT", "2 0039 od 03 ac 3255 RAM XXXXXXXX1111 29-09-2026 580\n15. RESULT")
		self.assertEqual(_vehicles_in(text), "OD03AB4135, OD03AC3255")

	def test_no_block_no_vehicle(self):
		from ivri_od.procurement.portal_sync import _vehicles_in

		self.assertEqual(_vehicles_in("nothing here"), "")
		self.assertEqual(_vehicles_in(""), "")

	def test_ac_note_no_is_the_part_between_the_slashes(self):
		from ivri_od.procurement.portal_sync import _lot_ac_note_in

		self.assertEqual(_lot_ac_note_in("1. Acceptance Note No.\nDW051105 / 0481 / 2025-2026\n2. Receive Date"), "0481")
		self.assertEqual(_lot_ac_note_in("Acceptance Note No. DW051105/12/2025-2026"), "12")
		self.assertEqual(_lot_ac_note_in("no note here"), "")

	def test_the_column_comes_after_the_lot_no(self):
		from ivri_od.procurement.portal_sync import with_vehicle

		cells = {"DC No.": "D1", "Lot No.": "5", "No.of Bag": "580"}
		self.assertEqual(list(with_vehicle(cells, "OD03AB4135", "0481")), ["DC No.", "Lot No.", "Vehicle No", "A.C. Note No.", "No.of Bag"])
		self.assertEqual(list(with_vehicle(with_vehicle(cells, "A"), "B")).count("Vehicle No"), 1)


class TestCmrStatement(unittest.TestCase):
	def test_season_is_read_as_crop_and_year(self):
		from ivri_od.procurement.cmr_statement import parse_season

		self.assertEqual(parse_season("Kharif(2025)"), ("kharif", "2025"))
		self.assertEqual(parse_season("Rabi 2025"), ("rabi", "2025"))
		self.assertEqual(parse_season(""), ("", ""))

	def test_two_vehicles_of_one_challan_are_split(self):
		from ivri_od.procurement.cmr_statement import split_vehicles

		self.assertEqual(split_vehicles("OD31P9471 ,OD31P9499"), ["OD31P9471", "OD31P9499"])
		self.assertEqual(split_vehicles("od03 ab4135"), ["OD03AB4135"])
		self.assertEqual(split_vehicles(""), [])

	def test_miller_code_is_taken_from_the_bracket(self):
		from ivri_od.procurement.cmr_statement import mill_code_of

		self.assertEqual(mill_code_of("SHREE SHYAMJI PADDY PROCESSING PVT LTD (M051007)"), "M051007")
		self.assertEqual(mill_code_of("Radhe Govind Food Products (Raw) (M050415)"), "M050415")
		self.assertEqual(mill_code_of("M051007"), "M051007")


class TestOwnVehicles(unittest.TestCase):
	def _doc(self, own_numbers):
		from unittest.mock import patch

		doc = frappe.new_doc("Vehicle Wise Statement")
		doc.season = "Kharif(2025)"
		for number, qty in (("OD01A0001", 100), ("OD02B0002", 200), ("OD03C0003", 300)):
			doc.append("items", {"vehicle_no": number, "ppc": "P(1)", "qty": qty, "km": 10, "rate": 50})
		with patch.object(vs, "own_vehicle_numbers", return_value=own_numbers):
			doc.recalculate()
		return doc

	def test_hired_first_own_last_no_voucher_for_own(self):
		doc = self._doc(["OD01A0001"])  # the first vehicle is an own vehicle
		self.assertEqual([r.vehicle_no for r in doc.items], ["OD02B0002", "OD03C0003", "OD01A0001"])
		self.assertEqual([r.vehicle_type for r in doc.items], ["Hired Vehicle", "Hired Vehicle", "Own Vehicle"])
		self.assertEqual([r.sl_no for r in doc.items], ["1", "2", ""])
		self.assertEqual([r.voucher_no for r in doc.items], ["1", "2", ""])  # 10000 and 15000 are one voucher each; the own vehicle has none
		self.assertEqual(doc.items[2].payment_mode, "")

	def test_totals_hired_own_and_grand(self):
		doc = self._doc(["OD01A0001"])
		self.assertEqual((doc.hired_qty, doc.hired_amount), (500, 25000))
		self.assertEqual((doc.own_qty, doc.own_amount), (100, 5000))
		self.assertEqual((doc.total_qty, doc.total_amount), (600, 30000))  # G. Total
		self.assertEqual(doc.total_vouchers, 2)  # own vehicles take no voucher

	def test_without_own_vehicles_everything_is_hired(self):
		doc = self._doc([])
		self.assertEqual((doc.own_qty, doc.own_amount, doc.total_vouchers), (0, 0, 3))
		self.assertEqual([r.sl_no for r in doc.items], ["1", "2", "3"])

	def test_the_print_has_totals_own_block_and_signatures(self):
		pf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		for part in ("G.TOTAL", "TOTAL VOUCHER", "NOS", "SIGNATURE OF AUTHORISED OFFICER", "SIGNATURE OF CUSTOM MILLER", "UNDERTAKING SUBMITTED FOR OWN", "OWN VEHICLE", "HIRED VEHICLE", "sign-gap"):
			self.assertIn(part, pf["html"], part)
		self.assertIn("own_block", pf["html"])  # the own block is kept together on a page

	def test_the_total_rows_are_compact_so_they_sit_just_below_each_other(self):
		pf = {d["name"]: d for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())}["Vehicle Wise Statement - Shyamji"]
		self.assertIn(".print-format .vws .sub td { font-size: 10px; padding: 2px 5px !important; line-height: 1.25; }", pf["css"])


class TestPpcRows(unittest.TestCase):
	def test_the_table_has_ppc_and_bags_and_the_form_script_follows_the_rules(self):
		item = {f["fieldname"]: f for f in json.loads((ROOT / "procurement" / "doctype" / "vehicle_wise_statement_item" / "vehicle_wise_statement_item.json").read_text())["fields"]}
		self.assertEqual((item["ppc"]["label"], item["ppc"]["read_only"], item["bags"]["label"], item["bags"]["fieldtype"]), ("PPC", 1, "Bags", "Int"))
		self.assertEqual(item["sl_no"]["fieldtype"], "Data")  # the S.L No is only on the first row of a vehicle
		script = (ROOT / "procurement" / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.js").read_text()
		self.assertIn("flt(row.qty) * flt(row.rate)", script)
		self.assertNotIn("flt(row.km)", script)  # the KM is only noted, it is not in the amount
		self.assertIn("copy_to_same_ppc", script)
		self.assertIn('"vehicle_lines"', json.dumps(["vehicle_lines"]))
		self.assertIn("vehicle_lines(doc)", json.loads((ROOT / "fixtures" / "print_format.json").read_text())[-2]["html"] + json.loads((ROOT / "fixtures" / "print_format.json").read_text())[-1]["html"] + "".join(d["html"] for d in json.loads((ROOT / "fixtures" / "print_format.json").read_text())))
		self.assertIn("ivri_od.procurement.vehicle_statement.vehicle_lines", (ROOT / "hooks.py").read_text())


class TestTableLook(unittest.TestCase):
	def test_ppc_comes_before_vehicle_no_and_the_table_text_wraps(self):
		item = json.loads((ROOT / "procurement" / "doctype" / "vehicle_wise_statement_item" / "vehicle_wise_statement_item.json").read_text())
		order = item["field_order"]
		self.assertLess(order.index("ppc"), order.index("vehicle_no"))
		self.assertLess(order.index("vehicle_no"), order.index("bags"))
		script = (ROOT / "procurement" / "doctype" / "vehicle_wise_statement" / "vehicle_wise_statement.js").read_text()
		self.assertIn("white-space: normal !important", script)  # headings and PPC names are not cut with "..."
		self.assertIn(".ivri-no-row-number .row-index { display: none !important; }", script)

	def test_the_vehicle_type_column_is_shown_in_the_table(self):
		item = {f["fieldname"]: f for f in json.loads((ROOT / "procurement" / "doctype" / "vehicle_wise_statement_item" / "vehicle_wise_statement_item.json").read_text())["fields"]}
		self.assertEqual((item["vehicle_type"]["in_list_view"], item["vehicle_type"]["read_only"]), (1, 1))


class TestVoucherDates(unittest.TestCase):
	def test_every_four_vehicles_share_a_date_and_the_next_four_the_next_day(self):
		self.assertEqual([vs.voucher_date("2026-11-04", i) for i in range(9)],
			["04.11.2026"] * 4 + ["05.11.2026"] * 4 + ["06.11.2026"])
		self.assertEqual(vs.voucher_date("2026-11-04", 2, per_date=2), "05.11.2026")
		self.assertEqual(vs.voucher_date("2026-11-30", 4), "01.12.2026")  # over the month end
		self.assertEqual(vs.voucher_date("", 0), "")  # no start date: left empty

	def test_all_vouchers_of_a_vehicle_get_the_same_date(self):
		doc = frappe._dict(items=[
			frappe._dict(vehicle_no=f"OD0{i}A000{i}", ppc="P", qty=1, amount=a, voucher_no=v, payment_mode="CASH", vehicle_type="Hired Vehicle", sl_no=str(i + 1), bags=1)
			for i, (a, v) in enumerate([(120000, "1,2,3"), (10000, "4"), (60000, "5,6"), (500, "7"), (700, "8"), (900, "9")])
		])
		got = vs.debit_vouchers(doc, "2026-11-04", 4)
		self.assertEqual([(v["voucher_no"], v["date"]) for v in got],
			[("1", "04.11.2026"), ("2", "04.11.2026"), ("3", "04.11.2026"),  # vehicle 1: 3 vouchers, one date
			 ("4", "04.11.2026"), ("5", "04.11.2026"), ("6", "04.11.2026"), ("7", "04.11.2026"),  # vehicles 2, 3, 4 on the same date
			 ("8", "05.11.2026"), ("9", "05.11.2026")])  # the next 4 vehicles: the next day
		self.assertEqual({v["date"] for v in vs.debit_vouchers(doc)}, {""})  # printed without a start date: no date


class TestPpcDistance(unittest.TestCase):
	def _doc(self):
		doc = frappe.new_doc("Vehicle Wise Statement")
		doc.miller, doc.season = "M", "Kharif(2025)"
		doc.append("items", {"vehicle_no": "OD01A0001", "ppc": "GHASIAN(S1051002)", "qty": 10, "km": 7, "rate": 53})  # typed before
		doc.append("items", {"vehicle_no": "OD01A0001", "ppc": "NODIST(X1)", "qty": 10, "km": 9, "rate": 40})
		return doc

	def test_the_km_is_fetched_from_the_distance_of_the_ppc(self):
		passes = [
			{"vehicle_no": "OD01A0001", "ppc": "GHASIAN(S1051002)", "bags": 5, "quantity": 10},
			{"vehicle_no": "OD01A0001", "ppc": "NODIST(X1)", "bags": 5, "quantity": 10},
			{"vehicle_no": "OD02B0002", "ppc": "TAMIAN(S1051012)", "bags": 5, "quantity": 10},
		]
		doc = self._doc()
		with patch.object(vs, "get_passes", return_value=passes), patch.object(vs, "own_vehicle_numbers", return_value=[]), \
			patch.object(vs, "ppc_distances", return_value={"S1051002": 48.0, "S1051012": 51.2}):
			doc.fetch_details()
		self.assertEqual([(r.ppc, r.km, r.rate) for r in doc.items],
			[("GHASIAN(S1051002)", 48.0, 53), ("NODIST(X1)", 9, 40), ("TAMIAN(S1051012)", 51.2, 0)])
		# the Distance of the master wins over the typed KM; a PPC with no Distance keeps the typed KM; the Rate typed is kept

	def test_the_field_is_in_the_ppc_master(self):
		d = json.loads((ROOT / "procurement" / "doctype" / "ppc_master" / "ppc_master.json").read_text())
		f = {x["fieldname"]: x for x in d["fields"]}
		self.assertEqual((f["distance"]["label"], f["distance"]["fieldtype"]), ("Distance", "Float"))
		self.assertEqual(d["field_order"][d["field_order"].index("district") + 1], "distance")


class TestOneDecimal(unittest.TestCase):
	def test_km_and_distance_show_one_decimal(self):
		item = {f["fieldname"]: f for f in json.loads((ROOT / "procurement" / "doctype" / "vehicle_wise_statement_item" / "vehicle_wise_statement_item.json").read_text())["fields"]}
		master = {f["fieldname"]: f for f in json.loads((ROOT / "procurement" / "doctype" / "ppc_master" / "ppc_master.json").read_text())["fields"]}
		self.assertEqual((item["km"]["fieldtype"], item["km"]["precision"]), ("Float", "1"))  # 51.2, not 51.200
		self.assertEqual((master["distance"]["fieldtype"], master["distance"]["precision"]), ("Float", "1"))
