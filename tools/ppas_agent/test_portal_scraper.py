"""Tests for the pure helpers of portal_scraper (no Chrome needed).

Run: python -m unittest test_portal_scraper  (from this folder)
"""

import unittest

from portal_scraper import trigger_hint, waits_for_own_trigger, only_clicks_for, click_starts_read, page_columns, lots_from_column, grid_matches_for, grid_to_table, looks_like_login, receipt_config_for, split_total_rows, table_match_for, click_triggers_for, oldest_first, date_column, detail_link, known_rows_for, newest_first, row_signature, mill_label_keys, open_read_for, document_labels, document_steps, file_extension, page_matches_row, row_tokens, pick_receipt_link, rows_to_cells, unique_headers


class TestPortalScraperHelpers(unittest.TestCase):
    def test_unique_headers(self):
        self.assertEqual(
            unique_headers(["Sl No", "", "Qty", "qty", "  Lot\n No "]),
            ["Sl No", "Column 2", "Qty", "qty 2", "Lot No"],
        )

    def test_rows_to_cells_keeps_extra_cells(self):
        rows = rows_to_cells(["A", "B"], [{"cells": ["1", "2", "3"]}])
        self.assertEqual(rows, [{"A": "1", "B": "2", "Column 3": "3"}])

    def test_pick_receipt_link_prefers_pdf_and_skips_pager_and_edit(self):
        links = [
            {"text": "Edit", "raw_href": "javascript:__doPostBack('g','Edit$0')", "href": ""},
            {"text": "2", "raw_href": "javascript:__doPostBack('g','Page$2')", "href": ""},
            {"text": "TC-1", "raw_href": "/docs/tc1.pdf", "href": "https://x.invalid/docs/tc1.pdf"},
        ]
        self.assertEqual(pick_receipt_link(links)["text"], "TC-1")

    def test_pick_receipt_link_postback_print_button(self):
        links = [{"text": "Print Receipt", "raw_href": "javascript:__doPostBack('g','Print$0')", "href": ""}]
        self.assertEqual(pick_receipt_link(links)["text"], "Print Receipt")

    def test_pick_receipt_link_by_section_label(self):
        # Transit Challan: the Action column button, chosen by the section's Receipt Link Text.
        links = [
            {"label": "View", "text": "View lnkView", "raw_href": "javascript:__doPostBack('g','View$0')"},
            {"label": "", "text": "btnPrintChallan", "raw_href": ""},
        ]
        self.assertEqual(pick_receipt_link(links, wanted_label="printchallan")["text"], "btnPrintChallan")
        self.assertEqual(pick_receipt_link(links, wanted_label="VIEW")["label"], "View")
        self.assertIsNone(pick_receipt_link(links, wanted_label="Download"))

    def test_receipt_config_for_page(self):
        config = [{"page_match": "CMR_TransitChallanView_WB.aspx", "link_text": "Print"}]
        url = "https://x.invalid/Receipt/CMR_TransitChallanView_WB.aspx?linkm=18"
        self.assertEqual(receipt_config_for(config, url), (True, "Print"))
        self.assertEqual(receipt_config_for(config, "https://x.invalid/DCStatusOfMiller.aspx"), (False, ""))

    def test_login_page_is_detected(self):
        login = '<form><input name="txtUser"><input type="password" name="txtPwd"> Enter Captcha</form>'
        self.assertTrue(looks_like_login(login, "https://x.invalid/Login.aspx"))
        challan = "<h2>Transit Challan</h2><table><tr><td>TC-1</td></tr></table>"
        self.assertFalse(looks_like_login(challan, "https://x.invalid/Print/TransitChallanPrint.aspx"))

    def test_receipt_config_only_for_its_tab(self):
        url = "https://x.invalid/Lot/LotSearch.aspx"
        receipts = [{"page_match": "LotSearch.aspx", "table_match": "Lot Search", "link_text": "Print"}]
        grids = [
            {"page_match": "LotSearch.aspx", "table_match": m} for m in ("Rejected Lot", "Pending Lot", "Lot Search")
        ]
        tab_bar = "Lot SearchRejected Lot For RRCPending Lot In For RRC"
        on_rejected = table_match_for(grids, url, {"table_title": tab_bar, "active_tab": "Rejected Lot For RRC"})
        on_search = table_match_for(grids, url, {"table_title": tab_bar, "active_tab": "Lot Search"})
        self.assertEqual((on_rejected, on_search), ("rejectedlot", "lotsearch"))
        self.assertEqual(receipt_config_for(receipts, url, on_search), (True, "Print"))
        self.assertEqual(receipt_config_for(receipts, url, on_rejected), (False, ""))
        # Without Table Match the setting covers the whole page.
        self.assertEqual(receipt_config_for([{"page_match": "LotSearch.aspx", "link_text": "Print"}], url), (True, "Print"))

    def test_dcro_transit_challan_reads_only_after_search_box(self):
        # Show loads years of rows: the read starts after a value is typed in the
        # table's search box (gvDCDetails_filter) and Enter is pressed.
        config = [{"page_match": "DCTransitChalanView", "triggers": "gvDCDetails_filter", "only": 1}]
        url = "https://x.invalid/Miller/DCTransitChalanView.aspx"
        self.assertEqual(click_triggers_for(config, url), ["gvdcdetailsfilter"])
        self.assertTrue(only_clicks_for(config, url))
        # Show is a generic ("g") click: it loads the rows but does not start a read.
        self.assertFalse(click_starts_read("1700|g|/Miller/DCTransitChalanView.aspx", url, True))
        self.assertFalse(only_clicks_for(config, "https://x.invalid/ViewDC.aspx"))
        # The menu button that opened the page (a "view" click on another page) does not count.
        self.assertFalse(click_starts_read("1700|g|/Miller/Home.aspx", url, True))
        self.assertFalse(click_starts_read("1700|t|/Miller/Home.aspx", url, True))
        self.assertFalse(click_starts_read("1700", url, True))
        self.assertTrue(click_starts_read("1700|t|/Miller/DCTransitChalanView.aspx", url, True))
        # Other pages: any Search-like click, as before.
        self.assertTrue(click_starts_read("1700|g|/Miller/Home.aspx", url, False))

    def test_menu_click_seen_late_does_not_read_transit_challan(self):
        # The menu click is noticed while the dashboard still shows; by the time the table
        # appears (after Show) Chrome is on DC Transit Challan: that page waits for Enter.
        config = [{"page_match": "DCTransitChalanView", "triggers": "gvDCDetails_filter", "only": 1}]
        page = "https://portal.pdsodisha.gov.in/BillingSystem/ACNoteBill/DCTransitChalanView"
        menu = "1700|g|/Home/Dashboard"
        self.assertFalse(waits_for_own_trigger(config, menu, "https://portal.pdsodisha.gov.in/Home/Dashboard"))
        self.assertTrue(waits_for_own_trigger(config, menu, page))
        self.assertTrue(waits_for_own_trigger(config, "1700|g|/BillingSystem/ACNoteBill/DCTransitChalanView", page))
        self.assertFalse(waits_for_own_trigger(config, "1700|t|/BillingSystem/ACNoteBill/DCTransitChalanView", page))
        # Pages without "Only On These Clicks" read as before.
        self.assertFalse(waits_for_own_trigger(config, menu, "https://portal.pdsodisha.gov.in/X/ViewDC"))

    def test_dcro_view_dc_reads_only_after_show(self):
        # View DC has many rows over the years: read only after the user sets filters and clicks Show.
        config = [{"page_match": "ViewDC", "triggers": "Show", "only": 1}]
        url = "https://portal.pdsodisha.gov.in/DeliveryCertificate/ViewDC"
        self.assertTrue(only_clicks_for(config, url))
        self.assertEqual(click_triggers_for(config, url), ["show"])
        # The menu click that opened the page, and a row's own View button, do not start a read.
        self.assertFalse(click_starts_read("1700|g|/Home/Dashboard", url, True))
        self.assertFalse(click_starts_read("1700|g|/DeliveryCertificate/ViewDC", url, True))
        self.assertTrue(click_starts_read("1700|t|/DeliveryCertificate/ViewDC", url, True))

    def test_waiting_message_names_the_page_trigger(self):
        config = [
            {"page_match": "ViewDC", "triggers": "Show", "only": 1},
            {"page_match": "DCTransitChalanView", "triggers": "gvDCDetails_filter", "only": 1},
            {"page_match": "MillerRoPDS", "triggers": "Save, dvmillerhistory", "only": 0},
        ]
        base = "https://portal.pdsodisha.gov.in/"
        self.assertEqual(
            trigger_hint(config, base + "DeliveryCertificate/ViewDC"),
            'click "Show" (pressing Enter in a box does not start the read)',
        )
        self.assertEqual(
            trigger_hint(config, base + "BillingSystem/ACNoteBill/DCTransitChalanView"),
            "type a value in the table's Search box and press Enter",
        )
        self.assertEqual(
            trigger_hint(config, base + "DeliveryCertificate/MillerRoPDS/Add"),
            'click "Save" or click "dvmillerhistory" (pressing Enter in a box does not start the read)',
        )
        self.assertEqual(trigger_hint(config, base + "Home/Dashboard"), "click Search")

    def test_view_dc_search_box_enter_also_reads(self):
        # View DC: Show, or a value typed in the DataTables Search box (tabledata_filter) + Enter.
        config = [{"page_match": "ViewDC", "triggers": "Show, tabledata_filter", "only": 1}]
        url = "https://portal.pdsodisha.gov.in/DeliveryCertificate/ViewDC"
        self.assertEqual(click_triggers_for(config, url), ["show", "tabledatafilter"])
        self.assertEqual(
            trigger_hint(config, url), "click \"Show\" or type a value in the table's Search box and press Enter"
        )

    def test_click_triggers_for_page(self):
        config = [{"page_match": "MillerRoPDS", "triggers": "dvmillerhistory, Save"}]
        url = "https://portal.pdsodisha.gov.in/DeliveryCertificate/MillerRoPDS/Add"
        self.assertEqual(click_triggers_for(config, url), ["dvmillerhistory", "save"])
        self.assertEqual(click_triggers_for(config, "https://x.invalid/ViewDC"), [])

    def test_oldest_first_decides_early_stop(self):
        newest_first = [{"DC No": "3", "DC Date": "05-03-2026"}, {"DC No": "2", "DC Date": "01/02/2026"}]
        oldest = [{"Sl#": "1", "Date": "07-01-2025"}, {"Sl#": "2", "Date": "10-01-2025"}]
        self.assertEqual(date_column(newest_first), "DC Date")
        self.assertFalse(oldest_first(newest_first))
        self.assertTrue(oldest_first(oldest))
        self.assertFalse(oldest_first([{"No": "A"}, {"No": "B"}]))  # no dates: first rows are kept

    def test_documents_picked_by_column_header(self):
        links = [
            {"ref": "a", "label": "Download", "text": "Download", "column": "Details"},
            {"ref": "b", "label": "Download", "text": "Download", "column": "AC Note Doc"},
        ]
        self.assertEqual(document_labels("Details, AC Note Doc"), ["Details", "AC Note Doc"])
        self.assertEqual(pick_receipt_link(links, "", "AC Note Doc")["ref"], "b")
        self.assertEqual(pick_receipt_link(links, "", "Details")["ref"], "a")
        self.assertEqual(pick_receipt_link([{"ref": "m", "label": "Miller", "column": "Print"}], "", "Miller")["ref"], "m")
        self.assertEqual((file_extension(b"%PDF-1.4"), file_extension(b"\xff\xd8\xff\xe0"), file_extension(b"<html>")), (".pdf", ".jpg", None))

    def test_dcro_transit_challan_documents(self):
        # The DCRO column is "Acnote Doc"; the setting says "AC Note Doc".
        links = [
            {"ref": "a", "label": "Details", "text": "Details", "column": "Details"},
            {"ref": "b", "label": "Download", "text": "Download", "column": "Acnote Doc"},
        ]
        self.assertEqual(pick_receipt_link(links, "", "AC Note Doc")["ref"], "b")
        self.assertEqual(document_steps("Details > Print, AC Note Doc"), [("Details", "Print"), ("AC Note Doc", "")])
        self.assertEqual(document_labels("Details > Print, AC Note Doc"), ["Details", "AC Note Doc"])
        self.assertEqual(document_steps("Print"), [("Print", "")])
        # SCMS Transit Challan: the agent picks the eye icon, then Print.
        self.assertEqual(document_steps("> Print"), [("", "Print")])
        self.assertEqual(document_steps(""), [])

    def test_document_page_must_belong_to_its_row(self):
        row = {
            "Sl#": "20", "KMS Year": "2025-26", "Depot Code": "DW051602", "DC Order No": "DCF051636",
            "MillerCode": "M051007", "No. of Bags(In kg.)": "580.00", "Vechicle No.": "OD03Y7755",
            "Driver Name": "SATYABAN BEHERA", "Driver Contact No.": "9777207376",
            "Contract No.": "BLN/52/OSCSC/76", "Date": "27/09/2026", "Acnote Doc": "Download",
        }
        tokens = row_tokens(row)
        self.assertEqual(
            sorted(tokens), sorted(["dw051602", "dcf051636", "m051007", "od03y7755", "9777207376", "bln/52/oscsc/76"])
        )
        own = "Miller Name & Code:SHREE (M051007) Contract No:BLN/52/OSCSC/76 Depot Code:DW051602 Vehicle No.:OD03Y7755 1 DCF051636 9777207376"
        other = "Miller Name & Code:SHREE (M051007) Contract No:BLN/52/OSCSC/66 Depot Code:DW051602 Vehicle No.:OD03AC3255 1 DCF051302 9078017884"
        self.assertTrue(page_matches_row(tokens, own))
        self.assertFalse(page_matches_row(tokens, other))
        self.assertTrue(page_matches_row([], other))

    def test_wings_tec_report(self):
        # The "Delivered" column holds a button whose label is the quantity.
        links = [{"ref": "a", "label": "25.50", "column": "Delivered"}, {"ref": "b", "label": "View", "column": "Action"}]
        self.assertEqual(detail_link(links, "Delivered")["ref"], "a")
        self.assertEqual(detail_link(links, "View")["ref"], "b")
        self.assertIsNone(detail_link(links, "Lots"))
        # The table has its own id; the section's Table Match is the div around it.
        tec = [{"page_match": "miller_tec_report", "table_match": "report_div"}]
        page = {"table_id": "example", "table_title": "", "table_ids": "example report_div main"}
        self.assertEqual(table_match_for(tec, "https://fciarms.in/ETec/miller_tec_report", page), "reportdiv")
        stack = [{"page_match": "Mill/tagging", "table_match": "rept_div"}]
        self.assertEqual(table_match_for(stack, "https://fciarms.in/Mill/tagging", {"table_ids": "report_div"}), "")

    def test_wings_e_tec_read_on_open_and_mill_labels(self):
        self.assertTrue(open_read_for(["Mill/e_tec"], "https://fciarms.in/Mill/e_tec?cyear=2025-26"))
        self.assertFalse(open_read_for(["Mill/e_tec"], "https://fciarms.in/Mill/tagging"))
        self.assertFalse(open_read_for(["", None], "https://fciarms.in/"))
        self.assertEqual(mill_label_keys("Mill ID, Miller Code"), (["Mill ID", "Miller Code"], ["millid", "millercode"]))

    def test_only_new_rows(self):
        # Serial numbers shift when rows are added on top: not part of the fingerprint.
        a = row_signature({"Sl#": "1", "TEC No": "T1", "Delivered": "10", "Action": "View"})
        self.assertEqual(a, row_signature({"Sl#": "7", "TEC No": " T1", "Delivered": "10", "Action": "Print"}))
        self.assertNotEqual(a, row_signature({"Sl#": "1", "TEC No": "T1", "Delivered": "11"}))
        self.assertTrue(newest_first([{"Date": "05/10/2026"}, {"Date": "01/10/2026"}]))
        self.assertFalse(newest_first([{"Date": "01/10/2026"}, {"Date": "05/10/2026"}]))
        self.assertFalse(newest_first([{"DC": "A"}, {"DC": "B"}]))
        known = [
            {"page_match": "e_tec", "table_match": "DataTables_Table_0", "sigs": ["a"]},
            {"page_match": "e_tec", "table_match": "DataTables_Table_1", "sigs": ["b"]},
            {"page_match": "miller_tec_report", "table_match": "", "sigs": ["c"]},
        ]
        self.assertEqual(known_rows_for(known, "https://x/Mill/e_tec?cyear=1", "datatablestable1"), {"b"})
        self.assertEqual(known_rows_for(known, "https://x/ETec/miller_tec_report", "reportdiv"), {"c"})
        self.assertIsNone(known_rows_for(known, "https://x/Mill/tagging", ""))

    def test_grid_matches_for_page(self):
        config = [
            {"page_match": "LotSearch.aspx", "table_match": "Rejected Lot"},
            {"page_match": "LotSearch.aspx", "table_match": "Pending Lot"},
            {"page_match": "DateWiseGunnyStockRegister.aspx", "table_match": "Gunny Stock Register Details"},
        ]
        self.assertEqual(grid_matches_for(config, "https://x.invalid/LotSearch.aspx"), ["rejectedlot", "pendinglot"])
        self.assertEqual(grid_matches_for(config, "https://x.invalid/DCStatusOfMiller.aspx"), [])

    def test_pick_receipt_link_none(self):
        self.assertIsNone(pick_receipt_link([{"text": "Select", "raw_href": "javascript:x()", "href": ""}]))


def th(text, rowspan=1, colspan=1):
    return [text, rowspan, colspan, True, None]


def td(text, rowspan=1, colspan=1, nested=None):
    return [text, rowspan, colspan, False, nested]


class TestMergedCells(unittest.TestCase):
    # Raw rows as JS_READ_GRID / JS_READ_DETAIL_HTML return them.

    def test_two_level_header_and_rowspan_rows(self):
        raw = [
            {"cells": [td("Lot details of DC/500", colspan=7)]},
            {"cells": [th("Sl#", 2), th("Lot No.", 2), th("Receipt", colspan=2), th("Depot", colspan=2), th("Status", 2)]},
            {"cells": [th("No Of Bag"), th("Qty(In Qtl)"), th("Code"), th("Date")]},
            {"cells": [td("1", 2), td("L-11", 2), td("580"), td("290.00"), td("D-01"), td("01-10-2026"), td("Accepted", 2)]},
            {"cells": [td("20"), td("10.00"), td("D-02"), td("02-10-2026")]},
            {"cells": [td("Total", colspan=2), td("600"), td("300.00"), td(""), td(""), td("")]},
        ]
        headers, data = grid_to_table(raw)
        self.assertEqual(
            headers,
            ["Sl#", "Lot No.", "Receipt - No Of Bag", "Receipt - Qty(In Qtl)", "Depot - Code", "Depot - Date", "Status"],
        )
        rows = rows_to_cells(headers, data)
        self.assertEqual(rows[1]["Lot No."], "L-11")  # carried down from the merged cell
        self.assertEqual(rows[1]["Receipt - No Of Bag"], "20")
        self.assertEqual(rows[1]["Status"], "Accepted")
        self.assertEqual((rows[2]["Sl#"], rows[2]["Lot No."]), ("Total", ""))
        self.assertEqual(len(rows), 3)

    def test_nested_brl_table_spreads_over_its_sub_columns(self):
        # SCMS DC lots: "BRL Lot Details" header group with a small table inside each data cell.
        raw = [
            {"cells": [th("Sl#", 2), th("Lot No.", 2), th("Bags", 2), th("BRL Lot Details", colspan=3)]},
            {"cells": [th("Lot No."), th("No Of Bag"), th("Qty(In Qtl)")]},
            {"cells": [td("1"), td("1001"), td("580"), td("", nested=[["12", "300", "150.00"], ["13", "280", "140.00"]])]},
            {"cells": [td("2"), td("1002"), td("400"), td("", nested=[])]},
        ]
        headers, data = grid_to_table(raw)
        self.assertEqual(
            headers,
            ["Sl#", "Lot No.", "Bags", "BRL Lot Details - Lot No.", "BRL Lot Details - No Of Bag", "BRL Lot Details - Qty(In Qtl)"],
        )
        rows = rows_to_cells(headers, data)
        self.assertEqual(rows[0]["BRL Lot Details - Lot No."], "12, 13")
        self.assertEqual(rows[0]["BRL Lot Details - Qty(In Qtl)"], "150.00, 140.00")
        self.assertEqual((rows[1]["Lot No."], rows[1]["BRL Lot Details - Lot No."]), ("1002", ""))
        self.assertEqual(len(headers), len(data[0]["cells"]))

    def test_dc_lot_table_header_rowspan_does_not_spill_into_first_lot(self):
        # SCMS DC Monitoring -> View -> gdvGetPassRegister: the header cells span
        # more rows than the header has, and a "Total" footer closes the table.
        names = ["Sl#", "Lot No.", "Date Of Receipt", "Miller Code", "Miller Name",
                 "Acceptance Note No.", "Bags", "Quantity (In Qtl.)", "If Receive Against BRL Stock"]
        lot = lambda sl, no, qty: {"cells": [
            td(sl), td(no), td("14/10/2025"), td("M000001"), td("SAMPLE MILLER"), td(f"AN/{no}"),
            td("580"), td(qty), td("NO"), td(""), td(""), td(""),
        ]}
        raw = [
            {"cells": [th(n, 3) for n in names] + [th("BRL Lot Details", colspan=3)]},
            {"cells": [th("Lot No."), th("No Of Bag"), th("Qty(In Qtl)")]},
            lot("1", "56", "289.74000"),
            lot("2", "57", "289.64000"),
            {"cells": [td(""), td(""), td(""), td(""), td(""), td("Total"), td("1160"), td("579.38000"),
                       td(""), td(""), td(""), td("")]},
        ]
        headers, data = grid_to_table(raw)
        self.assertEqual(headers[:9], names)
        self.assertEqual(len(headers), 12)
        records, totals = split_total_rows(data)
        rows = rows_to_cells(headers, records)
        self.assertEqual(len(rows), 2)
        self.assertEqual(list(rows[0])[:9], names)  # website column order
        footer = rows_to_cells(headers, totals)
        self.assertEqual((footer[0]["Acceptance Note No."], footer[0]["Bags"]), ("Total", "1160"))
        self.assertEqual((rows[0]["Sl#"], rows[0]["Lot No."], rows[0]["Quantity (In Qtl.)"]), ("1", "56", "289.74000"))
        self.assertEqual(rows[1]["Lot No."], "57")
        self.assertFalse(any(h.startswith("Column") for r in rows for h in r))

    def test_row_heading_rowspan_in_data_still_carries_down(self):
        raw = [
            {"cells": [th("Group"), th("Item")]},
            {"cells": [th("G1", 2), td("a")]},
            {"cells": [td("b")]},
        ]
        _headers, data = grid_to_table(raw)
        self.assertEqual([r["cells"] for r in data], [["G1", "a"], ["G1", "b"]])

    def test_dcro_view_dc_lot_quantity_columns(self):
        # Portal Site Section "Detail Table ID" of DCRO View DC: td[4] of each tbody row.
        self.assertEqual(
            page_columns("grdDepotFCIbody[4], grdDepotRRCbody[4]"),
            [("grdDepotFCIbody", 4), ("grdDepotRRCbody", 4)],
        )
        self.assertIsNone(page_columns("gdvGetPassRegister"))
        self.assertIsNone(page_columns(""))
        items = [
            {"id": "grdDepotFCIbody", "value": "288.94000", "row": ["1", "10/01/2025", "580", "288.94000"]},
            {"id": "grdDepotFCIbody", "value": "", "row": ["2", "", "", ""]},
            {"id": "grdDepotFCIbody", "value": "288.94000", "row": ["", "Total", "580", "288.94000"]},
            {"id": "grdDepotRRCbody", "value": "100.5", "row": ["1", "x", "y", "100.5"]},
        ]
        lots, totals = lots_from_column(items)
        self.assertEqual(
            lots,
            [
                {"DC Type": "FCI", "Lots": "288.94000"},
                {"DC Type": "RRC", "Lots": "100.5"},
            ],
        )
        self.assertEqual(totals, [{"DC Type": "FCI", "Lots": "288.94000"}])

    def test_split_total_rows(self):
        data = [{"cells": ["1", "L-1"]}, {"cells": ["", "Grand Total"]}, {"cells": ["Total:", "9"]}]
        records, totals = split_total_rows(data)
        self.assertEqual(records, [{"cells": ["1", "L-1"]}])
        self.assertEqual(len(totals), 2)

    def test_plain_table_without_th(self):
        headers, data = grid_to_table([{"cells": [td("A"), td("B")]}, {"cells": [td("1"), td("2")]}])
        self.assertEqual((headers, data[0]["cells"]), (["A", "B"], ["1", "2"]))


if __name__ == "__main__":
    unittest.main()
