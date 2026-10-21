# Copyright (c) 2026, Profezzo and Contributors
# See license.txt

import base64
import json
from io import BytesIO

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from ivri_od.procurement import portal_sync
from ivri_od.procurement.doctype.portal_data_extraction.portal_data_extraction import (
	begin_run,
	finish_run,
	import_rows,
)

# The tests make their own mill (make_test_mill): no Company / Fiscal Year test records needed.
IGNORE_TEST_RECORD_DEPENDENCIES = ["Mill Master"]

TEST_SITE = "_Test Portal"
TEST_SECTION = "Transit Challan"
# Mill No. picked on Portal Data Extraction (each mill has its own portal account).
TEST_MILL = "_TEST-MILL-1"
OTHER_MILL = "_TEST-MILL-2"


def make_test_mill(code: str = TEST_MILL) -> str:
	if not frappe.db.exists("Mill Master", code):
		mill = frappe.get_doc({"doctype": "Mill Master", "miller_code": code, "type": "RAW", "is_active": 1})
		mill.flags.ignore_links = True
		mill.insert(ignore_mandatory=True)  # no Company needed here
	return code


def make_extraction(site: str, mill: str = TEST_MILL):
	return frappe.get_doc({"doctype": "Portal Data Extraction", "site": site, "mill": make_test_mill(mill)}).insert()


def make_pdf() -> bytes:
	from pypdf import PdfWriter

	writer = PdfWriter()
	writer.add_blank_page(width=200, height=200)
	out = BytesIO()
	writer.write(out)
	return out.getvalue()


class UnitTestPortalSync(UnitTestCase):
	def test_normalize_cells_squashes_spaces_and_drops_blank_headers(self):
		cells = portal_sync.normalize_cells({" Challan  No ": " TC/01 ", "": "x", "Qty": 12})
		self.assertEqual(cells, {"Challan No": "TC/01", "Qty": "12"})

	def test_empty_row_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			portal_sync.normalize_cells({"A": " ", "B": ""})

	def test_record_key_uses_key_columns_case_insensitively(self):
		cells = {"Challan No": "TC/01", "Lot No": "L9", "Qty": "12"}
		self.assertEqual(portal_sync.build_record_key(cells, ["challan no", "LOT NO"]), "TC/01 | L9")

	def test_record_key_falls_back_to_whole_row_when_key_is_blank(self):
		cells = {"Challan No": "", "Qty": "12"}
		key = portal_sync.build_record_key(cells, ["Challan No"])
		self.assertEqual(json.loads(key), cells)

	def test_view_dc_kms_year_from_season_year(self):
		self.assertEqual(portal_sync.kms_year_from_season_year("2026"), "2025-26")
		self.assertEqual(portal_sync.kms_year_from_season_year(" 2025 "), "2024-25")
		self.assertEqual(portal_sync.kms_year_from_season_year("2000"), "1999-00")
		for kept in ("2025-26", "", "RABI", "20256"):
			self.assertEqual(portal_sync.kms_year_from_season_year(kept), kept)
		cells = {"KMS (Year)": "2026", "Season": "KHARIF", "Generated Date": "05-01-2026"}
		self.assertEqual(
			portal_sync.fix_section_cells("View DC", cells),
			{"KMS (Year)": "2025-26", "Season": "KHARIF", "Generated Date": "05-01-2026"},
		)
		self.assertEqual(portal_sync.fix_section_cells("Paddy Release", cells), cells)  # other sections as read

	def test_record_name_is_stable_and_scoped_by_section(self):
		a = portal_sync.build_record_name("SCMS", "Search Lot", "L1")
		self.assertEqual(a, portal_sync.build_record_name("SCMS", "Search Lot", "L1"))
		self.assertNotEqual(a, portal_sync.build_record_name("SCMS", "DC Monitoring", "L1"))

	def test_sensitive_columns_are_dropped(self):
		cells = portal_sync.normalize_cells({"Challan No.": "C1", "Aadhaar No": "XXXX1234", "PAN No": "P", "Bag": "5"})
		self.assertEqual(cells, {"Challan No.": "C1", "Bag": "5"})

	def test_serial_and_link_columns_do_not_change_key_or_hash(self):
		a = {"Sl#": "1", "DC NO.": "D1", "Qty": "10", "Column 11": "View"}
		b = {"Sl#": "7", "DC NO.": "D1", "Qty": "10", "Column 11": "Hide"}
		self.assertEqual(portal_sync.build_record_key(a, []), portal_sync.build_record_key(b, []))
		self.assertEqual(portal_sync.build_row_hash(a), portal_sync.build_row_hash(b))

	def test_filter_cells_from_page_filters(self):
		page_filters = [
			{"label": "KMS Year :", "id": "ctl00_ddlKMSYear", "value": "2025-2026"},
			{"label": "", "id": "ddlDepot", "value": "DG051601-BALANGIR"},
			{"label": "Miller", "id": "ddlMiller", "value": "--Select--"},
			{"label": "Aadhaar No", "id": "txtAadhaar", "value": "XXXX1234"},
		]
		columns = "KMS Year = kms\nDepot Name = depot\nMiller Name = miller\nAadhaar = aadhaar"
		self.assertEqual(
			portal_sync.filter_cells(columns, page_filters),
			{"KMS Year": "2025-2026", "Depot Name": "DG051601-BALANGIR"},
		)
		self.assertEqual([f["id"] for f in portal_sync.safe_page_filters(page_filters)][-1], "ddlMiller")

	def test_safe_pdf_name(self):
		self.assertEqual(portal_sync._safe_pdf_name("../../etc/pass wd.PDF", "PR-1"), "etc_pass_wd.pdf")
		self.assertEqual(portal_sync._safe_pdf_name("", "PR-1"), "PR-1.pdf")


class IntegrationTestPortalDataExtraction(IntegrationTestCase):
	PAGE_URL = "https://example.invalid/Receipt/CMR_TransitChallanView_WB.aspx?linkm=18"

	def setUp(self):
		if not frappe.db.exists("Portal Site", TEST_SITE):
			frappe.get_doc(
				{
					"doctype": "Portal Site",
					"site_name": TEST_SITE,
					"login_url": "https://example.invalid/",
					"sections": [
						{
							"section_name": TEST_SECTION,
							"page_match": "TransitChallanView",
							"key_columns": "Challan No",
						}
					],
				}
			).insert()
		self.extraction = make_extraction(TEST_SITE)

	def tearDown(self):
		frappe.db.rollback()

	def _import(self, rows, page_url=None):
		started = begin_run(
			self.extraction.name,
			total_rows=len(rows),
			pages=1,
			columns=["Challan No", "Qty"],
			page_url=page_url or self.PAGE_URL,
			page_heading="Transit Challan View",
		)
		result = import_rows(self.extraction.name, started["run"], json.dumps(rows))
		finish_run(self.extraction.name, started["run"], "Completed")
		result["section"] = started["section"]
		return result

	def test_section_named_from_page(self):
		site = frappe.get_doc("Portal Site", TEST_SITE)
		self.assertEqual(site.resolve_section(self.PAGE_URL), TEST_SECTION)
		self.assertEqual(
			site.resolve_section("https://x.invalid/Gunny/DateWiseGunnyStockRegister.aspx?a=1"),
			"Date Wise Gunny Stock Register",
		)
		self.assertEqual(site.resolve_section("https://x.invalid/Default.aspx", "Lot Search"), "Lot Search")
		self.assertEqual(site.resolve_section("https://x.invalid/", "", "SCMS Portal"), "SCMS Portal")

	def test_each_search_is_a_run_under_its_section(self):
		self._import([{"cells": {"Challan No": "TC-1", "Qty": "10"}}])
		other = self._import(
			[{"cells": {"Lot No": "L-1", "Qty": "3"}}],
			page_url="https://example.invalid/Receipt/LotSearch.aspx",
		)
		self.assertEqual(other["section"], "Lot Search")

		doc = frappe.get_doc("Portal Data Extraction", self.extraction.name)
		self.assertEqual([r.section for r in doc.runs], [TEST_SECTION, "Lot Search"])
		self.assertEqual([r.status for r in doc.runs], ["Completed", "Completed"])
		self.assertEqual((doc.records_extracted, doc.records_inserted), (2, 2))
		self.assertEqual(
			frappe.db.get_value("Portal Record", {"site": TEST_SITE, "section": "Lot Search"}, "summary"),
			"L-1 · 3",
		)

	def test_insert_update_unchanged_and_bad_row(self):
		first = self._import(
			[
				{"cells": {"Challan No": "TC-1", "Qty": "10"}},
				{"cells": {"Challan No": "TC-2", "Qty": "20"}},
			]
		)
		self.assertEqual((first["inserted"], first["failed"]), (2, 0))

		second = self._import(
			[
				{"cells": {"Challan No": "TC-1", "Qty": "10"}},
				{"cells": {"Challan No": "TC-2", "Qty": "25"}},
				{"cells": {"Challan No": " ", "Qty": ""}},
			]
		)
		self.assertEqual(
			(second["inserted"], second["updated"], second["unchanged"], second["failed"]), (0, 1, 1, 1)
		)

		name = portal_sync.build_record_name(TEST_SITE, TEST_SECTION, "TC-2", TEST_MILL)
		self.assertEqual(json.loads(frappe.db.get_value("Portal Record", name, "row_data"))["Qty"], "25")

		doc = frappe.get_doc("Portal Data Extraction", self.extraction.name)
		self.assertEqual(doc.status, "Completed")
		self.assertEqual(doc.runs[-1].records_updated, 1)
		self.assertIn("Row 3", doc.extraction_log)

	def test_receipt_saved_privately_once(self):
		receipt = {
			"filename": "challan TC-9.pdf",
			"content_b64": base64.b64encode(make_pdf()).decode(),
			"source_url": "https://example.invalid/r.pdf",
		}
		row = {"cells": {"Challan No": "TC-9", "Qty": "5"}, "receipt": receipt}

		self.assertEqual(self._import([row])["receipts"], 1)
		self.assertEqual(self._import([row])["receipts"], 0)

		name = portal_sync.build_record_name(TEST_SITE, TEST_SECTION, "TC-9", TEST_MILL)
		file_url = frappe.db.get_value("Portal Record", name, "receipt_file")
		self.assertTrue(file_url.startswith("/private/files/"))

	def test_bad_receipt_keeps_row_and_logs_warning(self):
		bad = {
			"cells": {"Challan No": "TC-7", "Qty": "1"},
			"receipt": {"filename": "x.pdf", "content_b64": base64.b64encode(b"<html>").decode()},
		}
		good = {"cells": {"Challan No": "TC-8", "Qty": "2"}}
		result = self._import([bad, good])
		self.assertEqual((result["inserted"], result["failed"], result["receipts"]), (2, 0, 0))
		self.assertTrue(any("Row 1: receipt not saved" in e for e in result["errors"]))
		name = portal_sync.build_record_name(TEST_SITE, TEST_SECTION, "TC-7", TEST_MILL)
		self.assertFalse(frappe.db.get_value("Portal Record", name, "receipt_file"))

	def test_new_serial_number_does_not_create_duplicate(self):
		lot_page = "https://example.invalid/Receipt/LotSearch.aspx"
		self._import([{"cells": {"Sl#": "1", "Lot No": "L-9", "Qty": "4"}}], page_url=lot_page)
		again = self._import([{"cells": {"Sl#": "3", "Lot No": "L-9", "Qty": "4"}}], page_url=lot_page)
		self.assertEqual((again["inserted"], again["unchanged"]), (0, 1))
		self.assertEqual(frappe.db.count("Portal Record", {"site": TEST_SITE, "section": "Lot Search"}), 1)

	def test_details_saved_kept_and_updated(self):
		lots = [{"Sl#": "1", "Lot No": "LOT-1", "Qty": "290"}, {"Sl#": "2", "Lot No": "LOT-2", "Qty": "300"}]
		row = {"cells": {"Challan No": "TC-50", "Qty": "590"}, "details": lots}
		self.assertEqual(self._import([row])["inserted"], 1)
		name = portal_sync.build_record_name(TEST_SITE, TEST_SECTION, "TC-50", TEST_MILL)
		doc = frappe.get_doc("Portal Record", name)
		self.assertEqual((doc.detail_count, len(doc.details)), (2, 2))
		self.assertEqual(doc.details[1].summary, "LOT-2 · 300")

		# Details not captured this time: keep the old ones.
		self.assertEqual(self._import([{"cells": row["cells"]}])["unchanged"], 1)
		self.assertEqual(len(frappe.get_doc("Portal Record", name).details), 2)

		# One more lot on the same DC: the record is updated, not duplicated.
		row["details"] = [*lots, {"Sl#": "3", "Lot No": "LOT-3", "Qty": "10"}]
		self.assertEqual(self._import([row])["updated"], 1)
		self.assertEqual(frappe.get_doc("Portal Record", name).detail_count, 3)

	def test_verify_detail_rows_against_portal_counts(self):
		from ivri_od.procurement.portal_checks import verify_detail_rows

		good_lots = [{"Lot No.": "56", "Quantity (In Qtl.)": "289.74"}, {"Lot No.": "57", "Quantity (In Qtl.)": "289.64"}]
		bad_lots = [
			{"Lot No.": "Lot No.", "Quantity (In Qtl.)": "Quantity (In Qtl.)", "Column 14": "58"},
			{"Lot No.": "59", "Quantity (In Qtl.)": "289.00"},
			{"Lot No.": "", "Acceptance Note No.": "Total", "Quantity (In Qtl.)": "578.38"},
		]
		portal = {"No. Of Lot": "2", "Receipt Qty(In Qtl.)": "579.38000"}
		self._import(
			[
				{
					"cells": {"Challan No": "DC-1", **portal},
					"details": good_lots,
					"details_footer": [{"Acceptance Note No.": "Total", "Quantity (In Qtl.)": "579.38"}],
				},
				{"cells": {"Challan No": "DC-2", **portal}, "details": bad_lots},
			]
		)
		result = verify_detail_rows(site=TEST_SITE, section=TEST_SECTION, quiet=1)
		self.assertEqual((result["records"], result["passed"], result["failed"]), (2, 1, 1))
		problems = " ".join(result["problems"][0]["problems"])
		for text in ("lots: portal 2, ERP 3", "Column N", "header text", "Total"):
			self.assertIn(text, problems)

		# Lots keep the portal's column order; the Total line is stored apart.
		doc = frappe.get_doc("Portal Record", portal_sync.build_record_name(TEST_SITE, TEST_SECTION, "DC-1", TEST_MILL))
		self.assertEqual(list(json.loads(doc.details[0].detail_data)), ["Lot No.", "Quantity (In Qtl.)"])
		self.assertEqual(json.loads(doc.details_footer)[0]["Acceptance Note No."], "Total")
		self.assertEqual(doc.detail_count, 2)

	def test_session_config_lists_receipt_pages(self):
		from ivri_od.procurement.doctype.portal_data_extraction.portal_data_extraction import get_session_config

		site = frappe.get_doc("Portal Site", TEST_SITE)
		site.sections[0].download_receipt = 1
		site.sections[0].receipt_link_text = "Print"
		site.save()
		config = get_session_config(self.extraction.name)
		self.assertEqual(
			config["receipt_links"], [{"page_match": "TransitChallanView", "link_text": "Print", "table_match": ""}]
		)

	def test_receipt_file_named_after_record(self):
		receipt = {"filename": "receipt_p1_r1_ab12.pdf", "content_b64": base64.b64encode(make_pdf()).decode()}
		self._import([{"cells": {"Challan No": "TC-77", "Qty": "5"}, "receipt": receipt}])
		name = portal_sync.build_record_name(TEST_SITE, TEST_SECTION, "TC-77", TEST_MILL)
		file_url = frappe.db.get_value("Portal Record", name, "receipt_file")
		self.assertIn("Transit_Challan_TC-77", file_url)

	def test_transit_pass_report(self):
		from ivri_od.procurement import portal_report as base

		receipt = {"filename": "c.pdf", "content_b64": base64.b64encode(make_pdf()).decode()}
		self._import([{"cells": {"Challan No": "TC-88", "Qty": "5"}, "receipt": receipt}])
		columns, data, *_ = base.execute({"site": TEST_SITE, "section": TEST_SECTION}, receipt_label="Challan")
		self.assertIn("Challan", [c["label"] for c in columns])
		self.assertTrue(data[0]["receipt"].startswith("/private/files/"))
		# The DC report has no document column.
		columns, *_ = base.execute({"site": TEST_SITE, "section": TEST_SECTION})
		self.assertNotIn("receipt", [c["fieldname"] for c in columns])

	def test_dc_summary_report(self):
		from ivri_od.procurement import portal_report as report

		lots = [{"Lot No": "LOT-1", "Qty": "290"}, {"Lot No": "LOT-2", "Qty": "300"}]
		self._import([{"cells": {"Sl#": "1", "Challan No": "TC-60", "Qty": "590"}, "details": lots}])

		filters = {"site": TEST_SITE, "section": TEST_SECTION}
		columns, data, *_ = report.execute(filters)
		labels = [c["label"] for c in columns]
		self.assertIn("Challan No", labels)
		self.assertNotIn("Sl#", labels)
		self.assertNotIn("Detail Rows", labels)  # "No. Of Lot" on the portal row already says it
		for hidden in ("Record", "Receipt"):
			self.assertNotIn(hidden, labels)
		# The key column (Challan No) opens the lots; each row knows its record.
		self.assertEqual([c["label"] for c in columns if c.get("opens_details")], ["Challan No"])
		self.assertEqual(data[0]["detail_count"], 2)
		details = report.get_record_details(data[0]["record"])
		self.assertEqual([d["Lot No"] for d in details["rows"]], ["LOT-1", "LOT-2"])
		self.assertEqual(details["footer"], [])
		self.assertEqual(len(data), 1)

		columns, data, *_ = report.execute({**filters, "show_details": 1})
		self.assertEqual(len(data), 2)
		self.assertIn("Detail: Lot No", [c["label"] for c in columns])

	def test_report_rows_in_portal_order(self):
		from ivri_od.procurement import portal_report

		rows = [{"cells": {"Challan No": f"TC-{n}", "Qty": "1"}, "row_no": i} for i, n in enumerate("CAB", start=1)]
		self._import(rows)
		_columns, data, *_ = portal_report.section_report({}, TEST_SECTION, site=TEST_SITE)
		self.assertEqual([d["c0"] for d in data], ["TC-C", "TC-A", "TC-B"])

	def test_section_from_tab_or_table_on_shared_page(self):
		site = frappe.get_doc("Portal Site", TEST_SITE)
		site.sections = []
		for name, match in (("Rejected Lot for RRC", "Rejected Lot"), ("Pending Lot In for RRC", "Pending Lot"), ("Lot Search", "Lot Search")):
			site.append("sections", {"section_name": name, "page_match": "LotSearch.aspx", "table_match": match})
		site.append("sections", {"section_name": "Gunny Stock Register Details", "page_match": "DateWiseGunny",
			"table_match": "Gunny Stock Register Details"})
		site.save()
		url = "https://x.invalid/Lot/LotSearch.aspx"
		self.assertEqual(site.resolve_section(url, table_info={"active_tab": "Rejected Lot For RRC"}), "Rejected Lot for RRC")
		self.assertEqual(site.resolve_section(url, table_info={"table_id": "gvPendingLotIn"}), "Pending Lot In for RRC")
		self.assertEqual(site.resolve_section(url, table_info={"table_title": "Lot Search Result"}), "Lot Search")
		# The text above the table can be the whole tab bar; the open tab decides.
		tab_bar = "Lot SearchRejected Lot For RRCPending Lot In For RRC"
		self.assertEqual(
			site.resolve_section(url, table_info={"table_title": tab_bar, "active_tab": "Pending Lot In For RRC"}),
			"Pending Lot In for RRC",
		)
		# Several sections on the page and nothing matched: named from the tab, not guessed.
		self.assertEqual(site.resolve_section(url, table_info={"active_tab": "Other Tab"}), "Other Tab")
		# Only one section on the page: used even when its table title was not found.
		self.assertEqual(
			site.resolve_section("https://x.invalid/DateWiseGunnyStockRegister.aspx"), "Gunny Stock Register Details"
		)


class IntegrationTestPortalManualEntry(IntegrationTestCase):
	DC_URL = "https://example.invalid/DC/DCStatusOfMiller.aspx"

	def setUp(self):
		from unittest.mock import patch

		from ivri_od.procurement import portal_manual

		self.manual = portal_manual
		site = frappe.get_doc(
			{
				"doctype": "Portal Site",
				"site_name": "_Test Portal Manual",
				"login_url": "https://example.invalid/",
				"sections": [
					{
						"section_name": "DC Monitoring",
						"page_match": "DCStatusOfMiller",
						"key_columns": "DC NO.",
						"filter_columns": "KMS Year = kms\nDepot Name = depot",
					},
					{"section_name": "Gunny Stock Register Details", "page_match": "DateWiseGunny", "key_columns": "Date - A"},
				],
			}
		)
		if not frappe.db.exists("Portal Site", site.site_name):
			site.insert()
		patcher = patch.object(portal_manual, "SITE", site.site_name)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.extraction = make_extraction(site.site_name)

	def tearDown(self):
		frappe.db.rollback()

	def _record(self, dc_no):
		name = portal_sync.build_record_name(self.manual.SITE, "DC Monitoring", dc_no, TEST_MILL)
		return frappe.get_doc("Portal Record", name)

	def _scrape_dc(self, cells, details=None):
		started = begin_run(
			self.extraction.name,
			total_rows=1,
			columns=list(cells),
			page_url=self.DC_URL,
			page_filters=json.dumps(
				[
					{"label": "KMS Year", "id": "ddlKMS", "value": "2025-2026"},
					{"label": "Depot", "id": "ddlDepot", "value": "DG051601"},
				]
			),
		)
		row = {"cells": cells, "row_no": 1}
		if details is not None:
			row["details"] = details
		result = import_rows(self.extraction.name, started["run"], json.dumps([row]))
		finish_run(self.extraction.name, started["run"], "Completed")
		return result

	def test_page_filters_saved_with_each_scraped_row(self):
		self._scrape_dc({"Sl#": "1", "DC NO.": "DCR-9", "DC Qty(In Qtl.)": "100"})
		cells = json.loads(self._record("DCR-9").row_data)
		self.assertEqual(list(cells)[:3], ["KMS Year", "Depot Name", "Sl#"])
		self.assertEqual((cells["KMS Year"], cells["Depot Name"]), ("2025-2026", "DG051601"))
		run = frappe.get_doc("Portal Data Extraction", self.extraction.name).runs[-1]
		self.assertEqual(json.loads(run.page_filters), {"KMS Year": "2025-2026", "Depot Name": "DG051601"})

	def test_manual_rows_and_lots_then_portal_replaces_them(self):
		form = self.manual.get_manual_form("dc_summary")
		self.assertEqual(form["common_fields"], ["KMS Year", "Depot Name"])
		self.assertEqual(form["key_columns"], ["DC NO."])

		row = {"Sl#": "1", "DC NO.": "DCR-1", "DC Qty(In Qtl.)": "100"}
		result = self.manual.save_manual_rows("dc_summary", [row, {}, {"DC Qty(In Qtl.)": "5"}], {"KMS Year": "2025-2026"}, TEST_MILL)
		self.assertEqual((result["inserted"], result["updated"]), (1, 0))
		self.assertEqual(len(result["errors"]), 1)  # the row without DC NO.
		self.assertIn("DC NO.", result["errors"][0])
		doc = self._record("DCR-1")
		self.assertEqual(doc.entry_source, "Manual")
		self.assertEqual(list(json.loads(doc.row_data))[:2], ["KMS Year", "Sl#"])

		# Entered again by hand: updated, not duplicated.
		result = self.manual.save_manual_rows("dc_summary", [{**row, "DC Qty(In Qtl.)": "110"}], mill_id=TEST_MILL)
		self.assertEqual((result["inserted"], result["updated"]), (0, 1))

		lots = [
			{"Sl#": "1", "Lot No.": "1", "Bags": "580", "Quantity (In Qtl.)": "288.9"},
			{"Acceptance Note No.": "Total", "Bags": "580", "Quantity (In Qtl.)": "288.9"},
		]
		self.assertEqual(self.manual.save_manual_lots("DCR-1", lots)["lots"], 1)
		doc = self._record("DCR-1")
		self.assertEqual((doc.detail_count, doc.details_source), (1, "Manual"))
		self.assertEqual(json.loads(doc.details_footer)[0]["Acceptance Note No."], "Total")
		with self.assertRaises(frappe.ValidationError):
			self.manual.save_manual_lots("DCR-404", lots)

		# The portal shows the same values: still taken over by the portal, lots kept.
		self._scrape_dc({**row, "DC Qty(In Qtl.)": "110"})
		doc = self._record("DCR-1")
		self.assertEqual((doc.entry_source, doc.details_source, doc.detail_count), ("Portal", "Manual", 1))

		# Portal lots replace the manual lots; after that nothing is entered by hand over them.
		self._scrape_dc(row, details=[{"Lot No.": "1", "Bags": "580"}, {"Lot No.": "2", "Bags": "580"}])
		doc = self._record("DCR-1")
		self.assertEqual((doc.details_source, doc.detail_count), ("Portal", 2))
		result = self.manual.save_manual_rows("dc_summary", [row], mill_id=TEST_MILL)
		self.assertEqual((result["skipped"], result["updated"]), (1, 0))
		self.assertIn("portal data has priority", result["errors"][0])
		with self.assertRaises(frappe.ValidationError):
			self.manual.save_manual_lots("DCR-1", lots)

	def test_gunny_rows_by_date_in_report_order(self):
		from ivri_od.procurement import portal_report

		rows = [
			{"Date - A": "Total", "OB OF GUNNY (in Bags) - B": "30"},
			{"Date - A": "11/01/2025", "OB OF GUNNY (in Bags) - B": "20"},
			{"Date - A": "10/01/2025", "OB OF GUNNY (in Bags) - B": "10"},
		]
		self.assertEqual(self.manual.save_manual_rows("gunny_stock", rows, mill_id=TEST_MILL)["inserted"], 3)
		columns, data, *_ = portal_report.section_report(
			{}, "Gunny Stock Register Details", site=self.manual.SITE, date_column="Date - A"
		)
		self.assertEqual([d["c0"] for d in data], ["10/01/2025", "11/01/2025", "Total"])
		self.assertEqual({d["entry_source"] for d in data}, {"Manual"})
		self.assertIn("entry_source", [c["fieldname"] for c in columns])
		# Every portal report starts with the Mill No.
		self.assertEqual((columns[0]["fieldname"], columns[0]["label"]), ("mill_id", "Mill No."))
		self.assertEqual({d["mill_id"] for d in data}, {TEST_MILL})
		with self.assertRaises(frappe.ValidationError):
			self.manual.save_manual_rows("gunny_stock", rows)  # no Mill No.


class IntegrationTestDcroReports(IntegrationTestCase):
	"""DCRO Paddy Release (Remaining Balance) and View DC (every search filter saved)."""

	SITE = "_Test DCRO"

	def setUp(self):
		from unittest.mock import patch

		from ivri_od.procurement import portal_manual

		self.manual = portal_manual
		if not frappe.db.exists("Portal Site", self.SITE):
			frappe.get_doc(
				{
					"doctype": "Portal Site",
					"site_name": self.SITE,
					"login_url": "https://example.invalid/",
					"sections": [
						{
							"section_name": "Paddy Release",
							"page_match": "MillerRoPDS",
							"extract_on_click": "Save, dvmillerhistory",
						},
						{"section_name": "View DC", "page_match": "ViewDC", "filter_columns": "*"},
					],
				}
			).insert()
		forms = {
			key: {**form, "site": self.SITE} if form.get("site") == "DCRO" else form
			for key, form in portal_manual.MANUAL_FORMS.items()
		}
		patcher = patch.object(portal_manual, "MANUAL_FORMS", forms)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.extraction = make_extraction(self.SITE)

	def tearDown(self):
		frappe.db.rollback()

	def _scrape(self, url, rows, page_filters=None, extraction=None):
		name = (extraction or self.extraction).name
		started = begin_run(name, total_rows=len(rows), page_url=url, page_filters=json.dumps(page_filters or []))
		import_rows(name, started["run"], json.dumps([{"cells": r, "row_no": i} for i, r in enumerate(rows, 1)]))
		finish_run(name, started["run"], "Completed")
		return started["section"]

	def test_session_config_lists_click_triggers(self):
		from ivri_od.procurement.doctype.portal_data_extraction.portal_data_extraction import get_session_config

		config = get_session_config(self.extraction.name)
		self.assertEqual(
			config["click_triggers"], [{"page_match": "MillerRoPDS", "triggers": "Save, dvmillerhistory", "only": 0}]
		)

	def test_paddy_release_remaining_balance(self):
		from ivri_od.procurement.report.paddy_release_from_dcro import paddy_release_from_dcro as report

		url = "https://portal.pdsodisha.gov.in/DeliveryCertificate/MillerRoPDS/Add"
		lifted, released = "Paddy Lifted (Own District) (in Qtl)", "Quantity of Paddy Released for Milling (Own District) (in Qtl)"
		other = "Quantity of Paddy Released for Milling (Other District) (in Qtl)"
		rows = [  # portal order is not date order; Paddy Lifted is a running total on the portal
			{"RO No.": "RO-2", "Date of Requistion": "10-01-2025", lifted: "56,484.91", released: "6000.00", other: "100", "Status of Released Order": "Approved"},
			{"RO No.": "RO-1", "Date of Requistion": "07-01-2025", lifted: "49579.05", released: "5100.00", other: "0.00", "Status of Released Order": "Approved"},
			{"RO No.": "RO-3", "Date of Requistion": "17-01-2025", lifted: "65451.23", released: "6000.00", other: "0", "Status of Released Order": "Rejected"},
		]
		self.assertEqual(self._scrape(url, rows), "Paddy Release")
		# Another mill's release (its own account) does not lower this mill's balance.
		other_mill = make_extraction(self.SITE, OTHER_MILL)
		self._scrape(
			url,
			[{"RO No.": "RO-9", "Date of Requistion": "08-01-2025", lifted: "900", released: "500", other: "0", "Status of Released Order": "Approved"}],
			extraction=other_mill,
		)
		with patch_site(report, self.SITE):
			columns, data, *_ = report.execute({"mill_id": TEST_MILL})
			# Filtered to one order: the released total still counts the earlier ones.
			_columns, filtered, *_ = report.execute({"search": "RO-2"})
			_columns, other_data, *_ = report.execute({"mill_id": OTHER_MILL})
		labels = [c["label"] for c in columns]
		self.assertEqual(labels.index("Remaining Balance"), labels.index(other) + 1)
		ro_no = columns[labels.index("RO No.")]["fieldname"]
		by_ro = {d[ro_no]: d["x0"] for d in data}
		# 49579.05 - 5100; 56484.91 - (5100 + 6000 + 100); rejected RO-3 releases nothing.
		self.assertEqual(by_ro, {"RO-1": 44479.05, "RO-2": 45284.91, "RO-3": 54251.23})
		self.assertEqual([d["x0"] for d in filtered], [45284.91])
		self.assertEqual([d["x0"] for d in other_data], [400.0])
		self.assertEqual([d[ro_no] for d in data], ["RO-1", "RO-2", "RO-3"])  # date order

	def test_view_dc_keeps_every_filter_and_manual_columns(self):
		filters = [
			{"label": "District :", "id": "ddlDistrict", "value": "BALANGIR"},
			{"label": "Season", "id": "ddlSeason", "value": "--Select--"},
			{"label": "Status", "id": "ddlStatus", "value": "Approved"},
		]
		section = self._scrape("https://x.invalid/DC/ViewDC", [{"DC No": "DC-1", "KMS (Year)": "2026", "Qty": "10"}], filters)
		self.assertEqual(section, "View DC")
		record = frappe.get_all("Portal Record", filters={"site": self.SITE, "section": "View DC"}, fields=["row_data"])[0]
		# KMS (Year): the season's year 2026 is saved as KMS year 2025-26.
		self.assertEqual(
			json.loads(record.row_data),
			{"District": "BALANGIR", "Status": "Approved", "DC No": "DC-1", "KMS (Year)": "2025-26", "Qty": "10"},
		)

		# Manual grid takes the columns of the last portal row; the same row is not saved over it.
		form = self.manual.get_manual_form("view_dc")
		self.assertEqual(form["columns"], ["District", "Status", "DC No", "KMS (Year)", "Qty"])
		self.assertEqual([f["form"] for f in self.manual.get_manual_forms("dcro")], ["paddy_release", "view_dc"])
		result = self.manual.save_manual_rows(
			"view_dc",
			# 2026 typed by hand is saved as 2025-26 too, so the first row is the portal row (not saved over it).
			[
				{"District": "BALANGIR", "Status": "Approved", "DC No": "DC-1", "KMS (Year)": "2026", "Qty": "10"},
				{"DC No": "DC-2", "KMS (Year)": "2025", "Qty": "5"},
			],
			mill_id=TEST_MILL,
		)
		self.assertEqual((result["inserted"], result["skipped"]), (1, 1))
		kms = frappe.get_all("Portal Record", filters={"site": self.SITE, "section": "View DC"}, pluck="row_data")
		self.assertEqual(sorted(json.loads(r)["KMS (Year)"] for r in kms), ["2024-25", "2025-26"])
		with self.assertRaises(frappe.ValidationError):
			self.manual.get_manual_form("paddy_release")  # not read from the portal yet: columns unknown

	def test_dc_transit_challan_saves_each_document(self):
		from ivri_od.procurement import portal_report

		pdf = base64.b64encode(make_pdf()).decode()
		from PIL import Image

		scan = BytesIO()
		Image.new("RGB", (20, 20), "white").save(scan, "JPEG")  # a scanned AC Note
		jpg = base64.b64encode(scan.getvalue()).decode()
		rows = [
			{
				"cells": {"DC No": "DC-9", "Qty": "290"},
				"row_no": 1,
				"documents": [
					{"label": "Details", "filename": "d.pdf", "content_b64": pdf},
					{"label": "AC Note Doc", "filename": "a.jpg", "content_b64": jpg},
				],
			},
			{
				"cells": {"DC No": "DC-10", "Qty": "100"},
				"row_no": 2,
				"documents": [{"label": "Details", "content_b64": base64.b64encode(b"<html>").decode()}, {"label": "AC Note Doc", "error": "no 'AC Note Doc' button"}],
			},
		]
		started = begin_run(self.extraction.name, total_rows=2, page_url="https://x.invalid/ACNoteBill/DCTransitChalanView")
		result = import_rows(self.extraction.name, started["run"], json.dumps(rows))
		self.assertEqual(result["receipts"], 2, result["errors"])
		self.assertEqual(len(result["errors"]), 2)  # not a PDF/image; no button
		# Same files again: not saved twice.
		self.assertEqual(import_rows(self.extraction.name, started["run"], json.dumps(rows[:1]))["receipts"], 0)

		columns, data, *_ = portal_report.section_report(
			{}, started["section"], site=self.SITE, document_columns=["Details", "AC Note Doc"]
		)
		labels = [c["label"] for c in columns]
		self.assertEqual(labels[0], "Mill No.")
		self.assertEqual(labels[-4:], ["Details", "AC Note Doc", "Last Seen On", "Entered From"])
		first = next(d for d in data if d["c0"] == "DC-9")
		self.assertTrue(first["doc0"].endswith(".pdf") and first["doc1"].endswith(".jpg"))
		self.assertEqual(next(d for d in data if d["c0"] == "DC-10")["doc0"], "")


def patch_site(report_module, site):
	"""Point a DCRO report at the test site."""
	from unittest.mock import patch

	from ivri_od.procurement import portal_report

	original = portal_report.section_report

	def section_report(filters, section, site_name="DCRO", **kwargs):
		kwargs.pop("site", None)
		return original(filters, section, site=site, **kwargs)

	return patch.object(report_module, "section_report", section_report)


class IntegrationTestWings(IntegrationTestCase):
	"""WINGS TEC Report (Delivered lines as detail rows), Stack Status, and their manual entry."""

	SITE = "_Test WINGS"
	TEC_URL = "https://example.invalid/ETec/miller_tec_report"
	STACK_URL = "https://example.invalid/Mill/tagging"

	def setUp(self):
		from unittest.mock import patch

		from ivri_od.procurement import portal_manual

		self.manual = portal_manual
		if not frappe.db.exists("Portal Site", self.SITE):
			frappe.get_doc(
				{
					"doctype": "Portal Site",
					"site_name": self.SITE,
					"login_url": "https://example.invalid/",
					"sections": [
						{
							"section_name": "TEC Report",
							"page_match": "ETec/miller_tec_report",
							"table_match": "report_div",
							"extract_on_click": "View",
							"detail_link_text": "Delivered",
						},
						{
							"section_name": "Stack Status",
							"page_match": "Mill/tagging",
							"table_match": "rept_div",
							"filter_columns": "*",
						},
						{
							"section_name": "Booking / Delivery Status",
							"page_match": "Mill/e_tec",
							"table_match": "DataTables_Table_0",
							"read_on_open": 1,
							"filter_columns": "KMS Year = cyear",
						},
						{
							"section_name": "Targets / Advanced Paddy",
							"page_match": "Mill/e_tec",
							"table_match": "DataTables_Table_1",
							"read_on_open": 1,
							"filter_columns": "KMS Year = cyear",
						},
					],
				}
			).insert()
		forms = {
			key: {**form, "site": self.SITE} if form.get("site") == "WINGS" else form
			for key, form in portal_manual.MANUAL_FORMS.items()
		}
		patcher = patch.object(portal_manual, "MANUAL_FORMS", forms)
		patcher.start()
		self.addCleanup(patcher.stop)
		self.extraction = make_extraction(self.SITE)

	def tearDown(self):
		frappe.db.rollback()

	def _scrape(self, url, rows, page_filters=None, table_ids="", table_id="example", mill_id="", extraction=None):
		name = (extraction or self.extraction).name
		started = begin_run(
			name,
			total_rows=len(rows),
			page_url=url,
			table_id=table_id,
			table_ids=table_ids,
			page_filters=json.dumps(page_filters or []),
			mill_id=mill_id,
		)
		import_rows(name, started["run"], json.dumps([dict(r, row_no=i) for i, r in enumerate(rows, 1)]))
		finish_run(name, started["run"], "Completed")
		return started["section"]

	def _records(self, section):
		return frappe.get_all(
			"Portal Record",
			filters={"site": self.SITE, "section": section},
			fields=["name", "row_data", "detail_count", "details_source", "entry_source"],
		)

	def test_tec_delivered_lines_and_stack_filters(self):
		lines = [{"Date": "01/10/2026", "Lot": "L1", "Qty": "10"}, {"Date": "02/10/2026", "Lot": "L2", "Qty": "20"}]
		section = self._scrape(
			self.TEC_URL,
			[{"cells": {"Sl No": "1", "TEC No": "TEC0001", "Delivered": "30.00"}, "details": lines}],
			table_ids="example report_div",
		)
		self.assertEqual(section, "TEC Report")
		tec = self._records("TEC Report")[0]
		self.assertEqual((tec.detail_count, tec.details_source), (2, "Portal"))

		section = self._scrape(
			self.STACK_URL,
			[{"cells": {"Stack No": "S-1", "Bags": "500"}}],
			page_filters=[{"label": "Depot", "id": "ddlDepot", "value": "FSD KANTABANJI"}],
			table_ids="tbl rept_div",
		)
		self.assertEqual(section, "Stack Status")
		# List columns: the last page read and when.
		last = frappe.db.get_value("Portal Data Extraction", self.extraction.name, ["last_section", "last_extracted_on"])
		self.assertEqual(last[0], "Stack Status")
		self.assertEqual(str(last[1])[:10], frappe.utils.today())
		cells = json.loads(self._records("Stack Status")[0].row_data)
		self.assertEqual((cells["Depot"], cells["Stack No"]), ("FSD KANTABANJI", "S-1"))

		# Manual entry: columns come from the portal reads; Delivered lines of a TEC entered by hand.
		self.assertIn("TEC No", self.manual.get_manual_form("tec_report")["columns"])
		form = self.manual.get_manual_form("tec_delivered")
		self.assertEqual((form["lots"], form["columns"]), (True, ["Date", "Lot", "Qty"]))
		self.manual.save_manual_rows("tec_report", json.dumps([{"TEC No": "TEC0002", "Delivered": "15.00"}]), mill_id=TEST_MILL)
		manual_tec = next(r for r in self._records("TEC Report") if r.entry_source == "Manual")
		parents = self.manual.get_parent_rows("tec_delivered", "TEC0002")
		self.assertEqual([p["value"] for p in parents], [manual_tec.name])
		r = self.manual.save_manual_lots(form="tec_delivered", parent=manual_tec.name, rows=json.dumps([{"Date": "03/10/2026", "Lot": "L9", "Qty": "15"}]))
		self.assertEqual(r["lots"], 1)
		# Lines read from the portal are never replaced by hand.
		with self.assertRaises(frappe.ValidationError):
			self.manual.save_manual_lots(form="tec_delivered", parent=tec.name, rows=json.dumps([{"Lot": "X"}]))
		self.assertIn("TEC", [f["label"] for f in self.manual.get_manual_forms("wings")][0])

	def test_mill_no_and_e_tec_tables(self):
		from ivri_od.procurement.doctype.portal_data_extraction.portal_data_extraction import get_session_config

		config = get_session_config(self.extraction.name)
		self.assertEqual(config["open_reads"], ["Mill/e_tec", "Mill/e_tec"])
		self.assertIn("Miller Code", config["mill_id_labels"])

		# e_tec: two tables of one page, each its own section; KMS Year from the address (cyear).
		# 41498: the WINGS portal's own mill code (not in Mill Master): only noted on the form.
		url = "https://example.invalid/Mill/e_tec?cyear=2025-26"
		cyear = [{"label": "cyear", "id": "cyear", "value": "2025-26"}]
		row = {"cells": {"Depot": "FSD KANTABANJI", "Booked": "500"}}
		self.assertEqual(
			self._scrape(url, [row], cyear, "DataTables_Table_0 DataTables_Table_0_wrapper", "DataTables_Table_0", "41498"),
			"Booking / Delivery Status",
		)
		target = {"cells": {"Variety": "Boiled Non FRK", "Target": "1000"}}
		self.assertEqual(
			self._scrape(url, [target], cyear, "DataTables_Table_1", "DataTables_Table_1", "41498"),
			"Targets / Advanced Paddy",
		)
		booking = self._records("Booking / Delivery Status")[0]
		self.assertEqual(json.loads(booking.row_data)["KMS Year"], "2025-26")
		# Rows are saved under the Mill No. picked on the form.
		self.assertEqual(frappe.db.get_value("Portal Record", booking.name, "mill_id"), TEST_MILL)
		self.assertEqual(frappe.db.get_value("Portal Data Extraction", self.extraction.name, "mill_id"), "41498")

		# Another mill (its own extraction) with the same row gets its own record; the first mill's is not touched.
		self._scrape(url, [row], cyear, "DataTables_Table_0", "DataTables_Table_0", extraction=make_extraction(self.SITE, OTHER_MILL))
		mills = sorted(
			frappe.get_all("Portal Record", {"site": self.SITE, "section": "Booking / Delivery Status"}, pluck="mill_id")
		)
		self.assertEqual(mills, [TEST_MILL, OTHER_MILL])

		# A row's mill code that is not in Mill Master (TEC "Mill": name - code) does not change the Mill No.
		self._scrape(self.TEC_URL, [{"cells": {"TEC No": "T9", "Mill": "SHREE MILL - 41498"}}], table_ids="report_div")
		tec = frappe.get_all("Portal Record", {"site": self.SITE, "section": "TEC Report"}, pluck="mill_id")
		self.assertEqual(tec, [TEST_MILL])

		# A row of another mill of Mill Master is refused: never saved under the picked mill.
		started = begin_run(self.extraction.name, total_rows=1, page_url=self.TEC_URL, table_ids="report_div")
		result = import_rows(
			self.extraction.name, started["run"], json.dumps([{"cells": {"TEC No": "T10", "Miller Code": OTHER_MILL}}])
		)
		self.assertEqual((result["inserted"], result["failed"]), (0, 1))
		self.assertIn(OTHER_MILL, result["errors"][0])

		# Logged in with another mill's account: the run is stopped before anything is saved.
		with self.assertRaises(frappe.ValidationError):
			begin_run(self.extraction.name, total_rows=1, page_url=self.TEC_URL, table_ids="report_div", mill_id=OTHER_MILL)

	def test_mill_no_required(self):
		from ivri_od.procurement.doctype.portal_data_extraction.portal_data_extraction import get_session_config

		with self.assertRaises(frappe.MandatoryError):
			frappe.get_doc({"doctype": "Portal Data Extraction", "site": self.SITE}).insert()
		frappe.db.set_value("Portal Data Extraction", self.extraction.name, "mill", None)
		with self.assertRaises(frappe.ValidationError):
			get_session_config(self.extraction.name)

	def test_record_saved_before_mills_is_kept(self):
		url = self.STACK_URL
		row = {"cells": {"Depot": "D1", "Total": "10"}}
		portal_sync.import_rows(self.SITE, "Stack Status", self.extraction.name, [row])  # no mill (as before mills)
		first = self._records("Stack Status")
		self.assertEqual(len(first), 1)
		self._scrape(url, [row], table_ids="rept_div")
		again = self._records("Stack Status")
		self.assertEqual([r.name for r in again], [first[0].name])  # taken over, not duplicated
		self.assertEqual(frappe.db.get_value("Portal Record", first[0].name, "mill_id"), TEST_MILL)

	def test_known_rows_sent_so_only_new_rows_are_read(self):
		from ivri_od.procurement.doctype.portal_data_extraction.portal_data_extraction import get_session_config

		self._scrape(
			"https://example.invalid/ETec/miller_tec_report",
			[{"cells": {"TEC No": "T1", "Delivered": "10"}, "row_sig": "sig-t1"}, {"cells": {"TEC No": "T2"}, "row_sig": "sig-t2"}],
			table_ids="report_div",
		)
		known = {k["page_match"]: k for k in get_session_config(self.extraction.name)["known_rows"]}
		self.assertEqual(sorted(known["ETec/miller_tec_report"]["sigs"]), ["sig-t1", "sig-t2"])
		self.assertEqual(known["ETec/miller_tec_report"]["table_match"], "report_div")
		# Unchanged rows keep their fingerprint; a re-read updates it.
		self._scrape(
			"https://example.invalid/ETec/miller_tec_report",
			[{"cells": {"TEC No": "T1", "Delivered": "10"}, "row_sig": "sig-t1b"}],
			table_ids="report_div",
		)
		self.assertIn("sig-t1b", get_session_config(self.extraction.name)["known_rows"][0]["sigs"])
		# Read Full Table: no known rows, the agent reads every row.
		frappe.db.set_value("Portal Data Extraction", self.extraction.name, "read_full_table", 1)
		self.assertEqual(get_session_config(self.extraction.name)["known_rows"], [])
		# Section with "Read Only New Rows" off is not listed.
		site = frappe.get_doc("Portal Site", self.SITE)
		frappe.db.set_value("Portal Data Extraction", self.extraction.name, "read_full_table", 0)
		for row in site.sections:
			row.read_new_only = 0 if row.section_name == "TEC Report" else 1
		site.save()
		pages = [k["page_match"] for k in get_session_config(self.extraction.name)["known_rows"]]
		self.assertNotIn("ETec/miller_tec_report", pages)
