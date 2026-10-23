# PPAS Agent (local Windows service)

Frappe talks to the PPAS Agent at `http://127.0.0.1:8765` while the user is logged into the PPAS portal in Chrome.

## Deploying fixes

The installed `PPAS Agent.exe` must be rebuilt from this folder after scraper changes:

1. Install dependencies: `flask`, `flask-cors`, `requests`, `pandas`, `beautifulsoup4`, `selenium`, `openpyxl`
2. Package `ppas_agent.py`, `ppas_scraper.py`, `portal_scraper.py`, and `ppas_launcher.py` with PyInstaller (same layout as the handover installer).
   Build the agent with `--collect-all selenium`, else Connect Session fails with
   "No module named 'selenium.webdriver.chrome.webdriver'":
   `py -m PyInstaller --noconfirm --onefile --noconsole --name "PPAS Agent" --collect-all selenium --collect-submodules flask_cors ppas_agent.py`
3. Re-run **PPAS Agent Installer.exe** on each client PC.

## Recent scraper fixes

- Reads `millerId` from the logged-in PPAS page instead of using only the hardcoded fallback.
- Refreshes cookies from Chrome before extraction.
- Accepts `configuration_id` / `season_id` on `/extract` (Frappe sends this when seasons are loaded).

## Dev run (without the .exe)

```bash
cd apps/ivri_od/tools/ppas_agent
python ppas_agent.py
```

## Portal extraction (SCMS, DCRO, WINGS)

Used by **Portal Data Extraction** in the ERP. Routes live under `/portal/*`
(`start`, `status`, `extract_now`, `result`, `receipt`, `close`); every call after
`/portal/start` must send the token it returned (`X-Portal-Token` header).

1. Connect Session opens Chrome on the site's login page. The user logs in by hand.
2. The user opens any page from the portal menu, sets filters and clicks Search.
   The agent never opens pages itself (direct links end the portal session).
3. The agent reads all pages of the result table (ASP.NET `Page$N` pager, DataTables,
   or a "Next" button) and saves each row's receipt PDF (direct link, postback
   download, or HTML receipt printed to PDF).
4. The ERP form pulls rows and receipts, names the section from the page URL or
   heading, and saves them as Portal Record.

`/health` returns `"portal": true`; the ERP refuses to use an older agent without it.
The ERP also checks `portal_version` (see `PORTAL_AGENT_MIN_VERSION` in
portal_data_extraction.js). Version 8 sends the page's search filters
(`page_filters`: label, id, value of each visible drop-down and text box outside
the result table); the section's "Page Filter Columns" picks the ones saved with
each row, e.g. KMS Year and Depot Name for DC Monitoring.

Row documents (section "Receipt Link Text", versions 13-14): several documents are
separated by commas and found by button label or column header, ignoring spaces
("AC Note Doc" finds the DCRO column "Acnote Doc"). `Details > Print` clicks
Details, then the Print button on the page that opens, so the portal's own print
format is saved instead of a screenshot of the page. `> Print` alone (SCMS Transit
Challan RRC) lets the agent pick the row button itself, then clicks Print;
`View > Print` (DCRO View DC) finds View_RRC and View_FCI. Chrome runs with
`--kiosk-printing` and "Save as PDF", so window.print() saves a PDF into the
download folder with no dialog (a manual Ctrl+P in that Chrome does the same).
A page that opens must show more than half of the row's id values (DC No.,
vehicle, contract, phone); otherwise it is not saved, so a document is never
attached to the wrong row. If the list changed after Back, the row is found again
by those values.

WINGS (fciarms.in, version 15): TEC Report (`ETec/miller_tec_report`, table in
div#report_div) and Stack Status (`Mill/tagging`, table in div#rept_div, page
filters saved as columns). "Table Match" also checks every id around the table
(`table_ids`). A row's detail button is found by its label or its column header
(TEC: the "Delivered" column). When the button runs a script instead of a link or
postback, the agent clicks it like a user and reads the table it shows (a pop-up,
loaded by AJAX, is then closed; a new tab is closed; a new page goes Back).

Version 16: Mill ID and pages with several tables. After login the agent reads
the mill from the dashboard (a field such as hdnmillercode, or text such as
"Mill ID : 41498"; words from the site's "Mill ID Labels") and again on each page
read, and sends it with every result. The ERP saves it on every Portal Record (a
row's own Miller Code / "Mill: NAME - 41498" column wins; else the Mill ID typed on
the Portal Data Extraction form), and the record name includes the mill, so two
mills never share a record. A section with "Read On Page Open" (WINGS
`Mill/e_tec`) is read as soon as the page loads, once per page load; a page with
several configured tables (Booking / Delivery Status = DataTables_Table_0,
Targets / Advanced Paddy = DataTables_Table_1) gives one result per table, and
`/portal/status` lists them in `result_ids`. Values in the page address (cyear)
count as page filters. When no Mill ID is found on the dashboard, the page is
saved in Portal_Debug as `*_dashboard.html`.

Version 19: only new or changed rows. Each row gets a fingerprint of its values
(`row_signature`, serial and button columns left out); the ERP keeps it on the
Portal Record and sends the known ones per section at `/portal/start`
(`known_rows`, sections with "Read Only New Rows"). A known row is skipped: no
detail pop-up, no document, not sent. When the table lists newest dates first,
reading stops at the first known row. "Read Full Table" on Portal Data Extraction
sends no known rows (every row read). Sessions stay open after a save; the ERP
shows the result in Chrome with `/portal/notify`.

Version 20: a document page may show a row value split up. SCMS Lot Search
shows the Depot "DG051601-RMC,Kantabanji" on the Acceptance Note as Depot Code
"DG051601" and RRC "RMC,Kantabanji"; the page now counts as this row's when every
part is on it (parts of 3+ characters only). Lot Search Receipt Link Text:
`Miller > printer` (the row's Miller copy, then the page's Print button, id "printer"; an element whose id is exactly the text after ">" is clicked first, "#printer" also works). Clicking it runs Chrome's own Print > Save as PDF
(no date/address header and footer), the same file a user saves by hand;
Chrome's Save button is not clicked, kiosk printing saves it.
SCMS documents (Lot Search Acceptance Note, Transit Challan RRC Transit Pass) are saved
with Margins: None (`NO_MARGIN_SITES` in portal_scraper.py). DCRO DC Transit Challan Details
are printed with no margins too (`NO_MARGIN_PAGES`: the page asks for it before Print is
clicked); View DC and the other DCRO pages keep Chrome's default margins.
DCRO DC Transit Challan (`NEW_TAB_DOCUMENT_PAGES`): a row's real links (Details) open in a
new tab, like Ctrl+click; the document is saved there and the tab closed. The list is never
left (it is loaded by AJAX and comes back empty after Back), so the row's AC Note Doc button
is still there. Buttons that run a script are clicked as before.

Session closed part way: when Chrome is closed (or crashes, or the portal stops answering)
during a read, the rows read till then are kept as a result (rows left on the open page are
kept without their documents, "not saved: Chrome was closed"). The ERP form saves every
waiting result before it ends a closed session. Rows are lost only if the agent program
itself is stopped during a read.
DCRO DC Transit Challan: `Details > printIcon, AC Note Doc` (Details, then the print
icon id="printIcon" in the page header; Chrome's own Save button is not needed).
The real Miller copy shows only "Name of the RRC Malmunda" (no "RMC" word), so a
split value matches when its code part (DW051105) and at least half of its parts are on the page.

Rows the agent cannot read can be entered by hand: RRC Detail from SCMS →
Manual Entry (procurement/portal_manual.py). A row read from the portal always
replaces a manual row with the same key.

Tests (no Chrome needed): `python -m unittest test_portal_scraper`
